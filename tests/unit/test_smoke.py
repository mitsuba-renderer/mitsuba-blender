import os

import bpy
import numpy as np


def test_mitsuba_import():
    import mitsuba as mi
    mi.set_variant('scalar_rgb')
    assert mi.variant() == 'scalar_rgb'
    for name in ('parse_dict', 'parse_file', 'write_file', 'transform_all'):
        assert hasattr(mi.parser, name)


def test_addon_registers(mi_addon):
    assert mi_addon in bpy.context.preferences.addons


def test_engine_available(mi_addon, fresh_scene):
    engine_ids = {getattr(cls, 'bl_idname', None)
                  for cls in bpy.types.RenderEngine.__subclasses__()}
    assert 'MITSUBA' in engine_ids
    fresh_scene.render.engine = 'MITSUBA'
    assert fresh_scene.render.engine == 'MITSUBA'


def test_render_dict(render_dict, compare_images):
    img = render_dict({
        'type': 'scene',
        'integrator': {'type': 'path', 'max_depth': 2},
        'sensor': {
            'type': 'perspective',
            'film': {
                'type': 'hdrfilm',
                'width': 16,
                'height': 16,
                'rfilter': {'type': 'box'},
            },
            'sampler': {'type': 'independent', 'sample_count': 2},
        },
        'emitter': {'type': 'constant', 'radiance': 0.5},
    }, spp=2)
    assert img.shape == (16, 16, 3)
    compare_images(img, np.full((16, 16, 3), 0.5), mean_tol=1e-4, rmse_tol=1e-4)


def test_harness_isolated_from_user_profile():
    '''tests/run.py points BLENDER_USER_RESOURCES at a throwaway directory so
    the addon install in conftest cannot touch the developer's real profile.'''
    user_resources = os.environ.get('BLENDER_USER_RESOURCES')
    assert user_resources, 'harness did not isolate BLENDER_USER_RESOURCES'
    assert bpy.utils.resource_path('USER').startswith(user_resources)
