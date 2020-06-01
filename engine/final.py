import bpy
import tempfile
import os
import numpy as np
from ..export.convert import SceneConverter
from ..export.export import set_path

class MitsubaRenderEngine(bpy.types.RenderEngine):

    bl_idname = "MITSUBA2"
    bl_label = "Mitsuba 2"
    bl_use_preview = False

    # Init is called whenever a new render engine instance is created. Multiple
    # instances may exist at the same time, for example for a viewport and final
    # render.
    def __init__(self):
        self.scene_data = None
        self.draw_data = None
        self.converter = SceneConverter()

    # When the render engine instance is destroy, this is called. Clean up any
    # render engine data here, for example stopping running render threads.
    def __del__(self):
        pass

    # This is the method called by Blender for both final renders (F12) and
    # small preview for materials, world and lights.
    def render(self, depsgraph):
        if not set_path():
            self.report({'ERROR'}, "Importing Mitsuba failed. Please verify the path to the library in the addon preferences.")

        from mitsuba.core import Bitmap, Struct
        b_scene = depsgraph.scene
        scale = b_scene.render.resolution_percentage / 100.0
        self.size_x = int(b_scene.render.resolution_x * scale)
        self.size_y = int(b_scene.render.resolution_y * scale)

        # Temporary workaround as long as the dict creation writes stuff to dict
        with tempfile.TemporaryDirectory() as dummy_dir:
            filepath = os.path.join(dummy_dir, "scene.xml")
            self.converter.set_filename(filepath)
            self.converter.scene_to_dict(depsgraph)
            mts_scene = self.converter.dict_to_scene()

        sensor = mts_scene.sensors()[0] # TODO: only export the camera used for render in this case
        mts_scene.integrator().render(mts_scene, sensor)
        render = np.array(sensor.film().bitmap(raw=True).convert(Bitmap.PixelFormat.RGBA, Struct.Type.Float32, srgb_gamma=False))
        # Here we write the pixel values to the RenderResult
        result = self.begin_result(0, 0, self.size_x, self.size_y)
        layer = result.layers[0].passes["Combined"]

        layer.rect = np.flip(render,0).reshape((self.size_x*self.size_y, 4))
        self.end_result(result)
