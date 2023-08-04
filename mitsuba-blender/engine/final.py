import bpy
import tempfile
import os
import os.path as osp
import subprocess
import numpy as np
from ..io.exporter import SceneConverter, downgrade
from glob import glob

from ipdb import set_trace

class MitsubaRenderEngine(bpy.types.RenderEngine):

    bl_idname = "MITSUBA"
    bl_label = "Mitsuba"
    bl_use_preview = False
    # Use Eevee nodes in look dev ("MATERIAL") shading mode in the viewport.
    bl_use_eevee_viewport = True

    # Init is called whenever a new render engine instance is created. Multiple
    # instances may exist at the same time, for example for a viewport and final
    # render.
    def __init__(self):
        self.scene_data = None
        self.draw_data = None
        self.converter = SceneConverter(render=False)

    # When the render engine instance is destroy, this is called. Clean up any
    # render engine data here, for example stopping running render threads.
    def __del__(self):
        pass

    # This is the method called by Blender for both final renders (F12) and
    # small preview for materials, world and lights.
    def render(self, depsgraph):
        b_scene = depsgraph.scene
        version = b_scene.mitsuba.version
        mitsubaV1exe = b_scene.mitsuba.mtsv1exe
        print(f"Use mitsuba version : {version}")
        
        import mitsuba as mi
        from mitsuba import set_variant
        set_variant(b_scene.mitsuba.variant)
        # need to call only setting a variant
        from . import custom_integrators
        custom_integrators.register()
        # ---
        from mitsuba import ScopedSetThreadEnvironment, Thread
        with ScopedSetThreadEnvironment(b_scene.thread_env):
            scale = b_scene.render.resolution_percentage / 100.0
            self.size_x = int(b_scene.render.resolution_x * scale)
            self.size_y = int(b_scene.render.resolution_y * scale)

            # Temporary workaround as long as the dict creation writes stuff to dict
            # dummy_dir = "/home/arpit/Downloads/test_render"
            with tempfile.TemporaryDirectory() as dummy_dir:
                filepath = os.path.join(dummy_dir, "scene.xml")
                self.converter.set_path(filepath)
                self.converter.scene_to_dict(depsgraph)
                curr_thread = Thread.thread()
                curr_thread.file_resolver().prepend(dummy_dir)
                mts_scene = self.converter.dict_to_scene()

                if version == "v3":
                    sensor = mts_scene.sensors()[0]
                    mts_scene.integrator().render(mts_scene, sensor)
                    render_results = sensor.film().bitmap().split()
                else:
                    print(f"exe path - {mitsubaV1exe}")

                    # write to disk
                    self.converter.dict_to_xml()
                    # call downgrade
                    folder = osp.dirname(filepath)
                    fns = glob(osp.join(folder, "*/*.xml"), recursive=True) +\
                                glob(osp.join(folder, "*.xml"), recursive=True)
                    for fname in fns:
                        print(f"Checking {fname}")
                        downgrade.convert(fname)
                    # ---
                    # issue subprocess command
                    # this needs to be a blocking thread
                    env = os.environ.copy()
                    mit1_dir = osp.dirname(mitsubaV1exe)
                    env["PATH"] = mit1_dir + ":" + env["PATH"]
                    env["LD_LIBRARY_PATH"] = mit1_dir + ":" + env["LD_LIBRARY_PATH"]
                    
                    # render exr
                    try:
                        result = subprocess.run([
                            mitsubaV1exe, filepath.replace(".xml", "_v1.xml")
                        ], capture_output=True, env = env)
                        # output file would be 
                        outfilePath = filepath.replace(".xml", "_v1.exr")
                        bitmap = mi.Bitmap(outfilePath)
                        render_results = bitmap.split()
                    except Exception as e:
                        print("v1 render process failed")
                        # blender error reporting
                        self.report({"WARNING"}, f"Something isn't right\n{e}")
                        return {"CANCELLED"}

            for result in render_results:
                buf_name = result[0].replace("<root>", "Combined")
                channel_count = result[1].channel_count() if result[1].channel_count() != 2 else 3

                self.add_pass(buf_name, channel_count, ''.join([f.name.split('.')[-1] for f in result[1].struct_()]))

            blender_result = self.begin_result(0, 0, self.size_x, self.size_y)

            for result in render_results:
                render_pixels = np.array(result[1])
                if result[1].channel_count() == 2:
                    # Add a dummy third channel
                    render_pixels = np.dstack((render_pixels, np.zeros((*render_pixels.shape[:2], 1))))
                #render_pixels = np.array(render.convert(Bitmap.PixelFormat.RGBA, Struct.Type.Float32, srgb_gamma=False))
                # Here we write the pixel values to the RenderResult
                buf_name = result[0].replace("<root>", "Combined")
                layer = blender_result.layers[0].passes[buf_name]
                # print(render_pixels.shape, self.size_x, self.size_y)
                # https://docs.blender.org/api/current/bpy.types.RenderEngine.html
                # need array of 3D color vecs
                # need to add alpha for some reason
                render_pixels = np.dstack((render_pixels, np.zeros((*render_pixels.shape[:2], 1))))
                tmp = np.flip(render_pixels, 0).reshape((self.size_x*self.size_y, -1))
                # adding alpha channel
                layer.rect = tmp 
            self.end_result(blender_result)
