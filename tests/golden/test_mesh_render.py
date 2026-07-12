"""Golden render test: a mesh scene must match a committed EXR reference.

Regenerate the references with: python3 tests/run.py tests/golden --update-refs
"""

import os
import sys

import bpy
import numpy as np
import pytest

REFS_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'refs')


def render_current_scene(mi_addon, tmp_path, spp=16):
    import mitsuba as mi
    mi.set_variant('scalar_rgb')
    bpy.context.scene.render.engine = 'MITSUBA'
    bpy.context.scene.render.resolution_x = 64
    bpy.context.scene.render.resolution_y = 64
    converter = sys.modules[mi_addon].io.exporter.SceneConverter(render=True)
    converter.export_ctx.directory = str(tmp_path)
    converter.scene_to_dict(bpy.context.evaluated_depsgraph_get())
    scene = converter.dict_to_scene()
    return np.array(mi.render(scene, spp=spp, seed=0))


def test_suzanne_golden(mi_addon, fresh_scene, compare_images, request,
                        tmp_path):
    import mitsuba as mi

    # Smooth-shaded Suzanne in place of the default cube
    bpy.data.objects.remove(bpy.data.objects['Cube'])
    bpy.ops.mesh.primitive_monkey_add(size=3.0, rotation=(1.1, 0.0, 0.6))
    bpy.ops.object.shade_smooth()
    bpy.data.objects['Light'].data.energy = 10000.0

    image = render_current_scene(mi_addon, tmp_path)
    assert image.shape == (64, 64, 3)

    ref_path = os.path.join(REFS_DIR, 'suzanne.exr')
    if request.config.getoption('--update-refs'):
        os.makedirs(REFS_DIR, exist_ok=True)
        mi.Bitmap(image).write(ref_path)
        pytest.skip(f'Updated reference {ref_path}')

    reference = np.array(mi.Bitmap(ref_path))
    compare_images(image, reference, mean_tol=0.005, rmse_tol=0.02)
