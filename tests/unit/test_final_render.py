"""Final render (F12) through the MITSUBA render engine."""

import os

import bpy
import numpy as np


def test_f12_default_cube(mi_addon, fresh_scene, tmp_path):
    scene = fresh_scene
    scene.render.engine = 'MITSUBA'
    scene.mitsuba.variant = 'scalar_rgb'
    scene.render.resolution_x = 64
    scene.render.resolution_y = 48
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(tmp_path / 'render.exr')
    scene.render.image_settings.file_format = 'OPEN_EXR'

    # The exporter may emit files relative to the current directory; keep
    # any such side effects inside the test sandbox.
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        result = bpy.ops.render.render(write_still=True)
    finally:
        os.chdir(old_cwd)
    assert result == {'FINISHED'}

    import mitsuba as mi
    img = np.array(mi.Bitmap(str(tmp_path / 'render.exr')))
    assert img.shape[:2] == (48, 64)
    # The default cube lit by a point light renders to a non-uniform image.
    rgb = img[:, :, :3]
    assert rgb.max() > 0.0
    assert rgb.std() > 0.01
