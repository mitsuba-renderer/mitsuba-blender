import gc
import numpy as np

from ..exporter.converter import SceneConverter
from ..logging import time_operation

def render_beauty(engine, depsgraph):
    import drjit as dr
    import mitsuba as mi

    if not depsgraph.scene.mitsuba_engine.debug_mode:
        mi.set_log_level(mi.LogLevel.Error)

    # Make sure to garbage collect previous scenes
    gc.collect()

    # Make sure to clear the Dr.Jit registry otherwise hidden and deleted objects / materials
    # will still be unnecessarily JIT compiled
    dr.detail.clear_registry()

    b_scene = depsgraph.scene
    mi.set_variant(b_scene.mitsuba_engine.variant)

    converter = SceneConverter(render=True, viewport=False)

    with mi.ScopedSetThreadEnvironment(b_scene.thread_env):
        scale = b_scene.render.resolution_percentage / 100.0
        engine.size_x = int(b_scene.render.resolution_x * scale)
        engine.size_y = int(b_scene.render.resolution_y * scale)

        try:
            engine.update_stats('Mitsuba', f'Converting scene ...')

            with time_operation('Convert scene'):
                scene_dict = converter.scene_to_dict(depsgraph)
                mi.Thread.thread().file_resolver().prepend(SceneConverter.TEMP_DIR.name)

            # Check if we should abort the export (important in heavy scenes)
            if engine.test_break():
                return

            engine.update_stats('Mitsuba', f'Loading scene ...')

            with time_operation('Load scene'):
                mts_scene = mi.load_dict(scene_dict, parallel=True)

            # Check if we should abort the export (important in heavy scenes)
            if engine.test_break():
                return

            sensor = mts_scene.sensors()[0]
            total_spp = sensor.sampler().sample_count()
            accum_spp = 0
            if depsgraph.scene.mitsuba_engine.render_progressive:
                spp = 1
            else:
                spp = total_spp

            pixel_buffers = {}

            while accum_spp < total_spp:
                # Check if we should abort the export (important in heavy scenes)
                if engine.test_break():
                    return

                engine.update_stats('Mitsuba', f'Rendering {accum_spp} / {total_spp} samples ...')

                with time_operation(f'Render'):
                    img = mi.render(mts_scene, sensor=sensor, spp=spp)

                # Regularly check if we should abort the export (important in heavy scenes)
                if engine.test_break():
                    return

                aov_names = mts_scene.integrator().aov_names()
                if img.shape[2] == len(aov_names):
                    # Check if aovs are stored directly in the RGB channels
                    img_tmp = np.array(img)
                    img = np.zeros(shape=(img.shape[0], img.shape[1], 3+len(aov_names)))
                    img[:, :, 3:] = img_tmp[:, :, :]
                elif len(aov_names) + 3 != img.shape[2]:
                    # Check if nested integrator is stored directly in the RGB channels
                    aov_names = aov_names[4:]

                channel_names = ['R', 'G', 'B'] + aov_names

                bmp = mi.Bitmap(img, channel_names=channel_names)
                bitmaps = bmp.split()

                # Register the render output channels on the first pass
                if not depsgraph.scene.mitsuba_engine.render_progressive or spp == 1:
                    with time_operation(f'Register the render output'):
                        for name, bmp in bitmaps:
                            buf_name = name.replace("<root>", "Combined")
                            channel_count = bmp.channel_count() if bmp.channel_count() != 2 else 3
                            engine.add_pass(buf_name, channel_count, ''.join([f.name.split('.')[-1] for f in bmp.struct_()]))

                # Regularly check if we should abort the export (important in heavy scenes)
                if engine.test_break():
                    return

                with time_operation(f'Display results'):
                    result = engine.begin_result(0, 0, engine.size_x, engine.size_y)
                    for name, bmp in bitmaps:
                        if name == "<root>":
                            name = "Combined"
                            bmp = bmp.convert(mi.Bitmap.PixelFormat.RGBA, mi.Struct.Type.Float32, srgb_gamma=False)

                        pixels = np.array(bmp, dtype=np.float32)

                        if len(pixels.shape) == 2:
                            pixels = pixels[:, :, None]

                        if name in pixel_buffers:
                            pixels = (pixels * spp + pixel_buffers[name] * accum_spp) / (accum_spp + spp)

                        pixel_buffers[name] = pixels

                        # Add a dummy third channel if necessary
                        if bmp.channel_count() == 2:
                            pixels = np.dstack((pixels, np.zeros((*pixels.shape[:2], 1))))

                        pixels = np.flip(pixels, 0)

                        # Write the pixel values to the RenderResult
                        layer = result.layers[0].passes[name]
                        mi.blender.write_blender_framebuffer(pixels.astype(np.float32), layer.as_pointer())

                    accum_spp += spp
                    spp = min(total_spp - accum_spp, spp * 2)

                    engine.end_result(result)

            engine.update_stats('Mitsuba', f'Rendering done ({total_spp} samples)')
        except Exception as e:
            engine.report({"WARNING"}, f"Error: {str(e)}")
