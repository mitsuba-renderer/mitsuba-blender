import tempfile

import bpy
import numpy as np
from ..io.exporter import SceneConverter

class MitsubaRenderEngine(bpy.types.RenderEngine):

    bl_idname = "MITSUBA"
    bl_label = "Mitsuba"
    bl_use_preview = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.converter = SceneConverter(render=True)

    # This is the method called by Blender for both final renders (F12) and
    # small preview for materials, world and lights.
    def render(self, depsgraph):
        from mitsuba import set_variant
        b_scene = depsgraph.scene
        set_variant(b_scene.mitsuba.variant)

        scale = b_scene.render.resolution_percentage / 100.0
        self.size_x = int(b_scene.render.resolution_x * scale)
        self.size_y = int(b_scene.render.resolution_y * scale)

        # Temporary files (meshes, textures) written during the export must
        # survive until the scene has been loaded.
        with tempfile.TemporaryDirectory() as export_dir:
            self.converter.export_ctx.directory = export_dir
            self.converter.scene_to_dict(depsgraph)
            mts_scene = self.converter.dict_to_scene()

        sensor = mts_scene.sensors()[0]
        mts_scene.integrator().render(mts_scene, sensor)
        render_results = sensor.film().bitmap().split()

        for result in render_results:
            buf_name = result[0].replace("<root>", "Combined")
            if buf_name == 'Combined':
                # The root image goes to the built-in Combined pass
                continue
            channel_count = result[1].channel_count() if result[1].channel_count() != 2 else 3

            self.add_pass(buf_name, channel_count, ''.join([f.name.split('.')[-1] for f in result[1].struct_()]))

        blender_result = self.begin_result(0, 0, self.size_x, self.size_y)

        for result in render_results:
            render_pixels = np.array(result[1])
            if result[1].channel_count() == 2:
                # Add a dummy third channel
                render_pixels = np.dstack((render_pixels, np.zeros((*render_pixels.shape[:2], 1))))
            # Here we write the pixel values to the RenderResult
            buf_name = result[0].replace("<root>", "Combined")
            if buf_name == 'Combined' and render_pixels.shape[2] == 3:
                # Blender's Combined pass is always RGBA
                render_pixels = np.dstack((render_pixels, np.ones((*render_pixels.shape[:2], 1))))
            layer = blender_result.layers[0].passes[buf_name]
            layer.rect = np.flip(render_pixels, 0).reshape((self.size_x*self.size_y, -1))
        self.end_result(blender_result)
