"""Final render (F12) through the MITSUBA render engine."""

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

    assert bpy.ops.render.render(write_still=True) == {'FINISHED'}

    import mitsuba as mi
    img = np.array(mi.Bitmap(str(tmp_path / 'render.exr')))
    assert img.shape[:2] == (48, 64)
    # The default cube lit by a point light renders to a non-uniform image.
    rgb = img[:, :, :3]
    assert rgb.max() > 0.0
    assert rgb.std() > 0.01


def test_f12_aov_passes(mi_addon, fresh_scene, tmp_path):
    scene = fresh_scene
    scene.render.engine = 'MITSUBA'
    scene.mitsuba.variant = 'scalar_rgb'
    scene.render.resolution_x = 32
    scene.render.resolution_y = 32
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(tmp_path / 'passes.exr')
    scene.render.image_settings.file_format = 'OPEN_EXR_MULTILAYER'

    scene.mitsuba.active_integrator = 'aov'
    aov = scene.mitsuba.available_integrators.aov
    aov.depth = True
    aov.sh_normal = True
    aov.uv = True  # Two channels: exercises the padding to three

    assert bpy.ops.render.render(write_still=True) == {'FINISHED'}

    import mitsuba as mi
    bitmap = mi.Bitmap(str(tmp_path / 'passes.exr'))
    pixels = np.array(bitmap)
    layers = {}
    channels = {}
    # Channels are named <render layer>.<pass>.<channel>
    for index, field in enumerate(bitmap.struct_()):
        _, pass_name, channel = field.name.rsplit('.', 2)
        layers.setdefault(pass_name, []).append(pixels[:, :, index])
        channels.setdefault(pass_name, []).append(channel)
    layers = {name: np.dstack(planes) for name, planes in layers.items()}

    # 'path' is the image rendered by the nested path integrator
    assert {'depth', 'sh_normal', 'uv', 'path'} <= layers.keys()
    depth = layers['depth']
    assert depth.shape[2] == 1
    assert depth.max() > 0.0, 'the cube must be visible in the depth pass'
    normal = layers['sh_normal']
    assert normal.shape[2] == 3
    hit = depth[:, :, 0] > 0
    norms = np.linalg.norm(normal[hit], axis=-1)
    # AOVs average over samples, so only pixels fully covered by the cube
    # carry a unit shading normal; silhouette pixels mix in zeros.
    unit = np.isclose(norms, 1.0, atol=1e-2)
    assert unit.mean() > 0.5
    # The UV AOV has two channels and is padded with an empty third one
    uv = layers['uv']
    assert uv.shape[2] == 3
    assert set(channels['uv']) == {'U', 'V', 'A'}
    assert np.all(uv[:, :, channels['uv'].index('A')] == 0.0)
    assert uv.max() > 0.0


def test_f12_combined_is_linear(mi_addon, fresh_scene, tmp_path):
    scene = fresh_scene
    for b_object in list(scene.collection.all_objects):
        if b_object.type != 'CAMERA':
            bpy.data.objects.remove(b_object, do_unlink=True)
    background = scene.world.node_tree.nodes['Background']
    background.inputs['Color'].default_value = (0.5, 0.5, 0.5, 1.0)
    background.inputs['Strength'].default_value = 1.0

    scene.render.engine = 'MITSUBA'
    scene.mitsuba.variant = 'scalar_rgb'
    scene.render.resolution_x = 32
    scene.render.resolution_y = 32
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(tmp_path / 'gray.exr')
    scene.render.image_settings.file_format = 'OPEN_EXR'

    assert bpy.ops.render.render(write_still=True) == {'FINISHED'}

    import mitsuba as mi
    img = np.array(mi.Bitmap(str(tmp_path / 'gray.exr')))
    rgb = img[:, :, :3]
    # A mid-gray emitter must come out at 0.5 in the linear EXR: no view
    # transform or gamma may be baked into the Combined pass.
    assert np.allclose(rgb, 0.5, atol=5e-3), \
        f'expected linear 0.5, got mean {rgb.mean():.4f}'
