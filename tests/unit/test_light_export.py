"""Unit tests for the Blender light to Mitsuba emitter converters."""

import importlib
import math
import types

import bpy
import numpy as np
import pytest
from bpy_extras.io_utils import axis_conversion
from mathutils import Matrix, Vector


@pytest.fixture(scope='session')
def lights(mi_addon):
    return importlib.import_module(f'{mi_addon}.convert.export.lights')


@pytest.fixture
def export_ctx(mi_addon, tmp_path):
    import mitsuba as mi
    mi.set_variant('scalar_rgb')
    module = importlib.import_module(f'{mi_addon}.io.exporter.export_context')
    ctx = module.ExportContext()
    ctx.directory = str(tmp_path)
    ctx.axis_mat = axis_conversion(to_forward='-Z', to_up='Y').to_4x4()
    return ctx


@pytest.fixture
def log_capture(export_ctx):
    logs = []
    export_ctx.log = lambda msg, level='INFO': logs.append((level, msg))
    return logs


def make_light(light_type, name='TestLight', location=(0, 0, 0),
               rotation=(0, 0, 0), scale=(1, 1, 1), **data_props):
    data = bpy.data.lights.new(name, light_type)
    for key, value in data_props.items():
        setattr(data, key, value)
    obj = bpy.data.objects.new(name, data)
    obj.location = location
    obj.rotation_euler = rotation
    obj.scale = scale
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.update()
    return obj


def emitted_direction(export_ctx, obj):
    """The world-space emission direction of a Blender light, in Mitsuba
    coordinates (lights emit along their local -Z axis)."""
    direction = export_ctx.axis_mat.to_3x3() \
        @ obj.matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0))
    return np.array(direction.normalized())


def to_world_z_axis(params):
    """The +Z axis of an exported to_world transform."""
    matrix = np.array(params['to_world'].matrix)
    return matrix[:3, 2] / np.linalg.norm(matrix[:3, 2])


def test_point_light(fresh_scene, export_ctx, lights):
    obj = make_light('POINT', location=(1, 2, 3), energy=100.0,
                     color=(1.0, 0.5, 0.25), shadow_soft_size=0.0)
    params = lights.convert_light(export_ctx, obj)
    assert params['type'] == 'point'
    intensity = 100.0 / (4.0 * math.pi)
    assert params['intensity']['value'] == \
        pytest.approx([intensity, 0.5 * intensity, 0.25 * intensity])
    expected_pos = export_ctx.axis_mat @ Vector((1, 2, 3))
    assert params['position'] == pytest.approx(list(expected_pos))

    import mitsuba as mi
    assert mi.load_dict(params) is not None


def test_point_light_with_radius(fresh_scene, export_ctx, lights):
    obj = make_light('POINT', location=(0, 0, 1), energy=100.0,
                     color=(1.0, 1.0, 1.0), shadow_soft_size=0.5)
    params = lights.convert_light(export_ctx, obj)
    assert params['type'] == 'sphere'
    assert params['radius'] == pytest.approx(0.5)
    assert params['bsdf'] == {
        'type': 'diffuse',
        'reflectance': {'type' : 'rgb', 'value' : 0.0}
    }
    # The sphere must emit the same total power: L = P / (4 pi^2 r^2)
    radiance = 100.0 / (4.0 * math.pi ** 2 * 0.5 ** 2)
    assert params['emitter']['type'] == 'area'
    assert params['emitter']['radiance']['value'] == \
        pytest.approx([radiance] * 3)

    import mitsuba as mi
    assert mi.load_dict(params) is not None


def test_spot_light(fresh_scene, export_ctx, lights):
    obj = make_light('SPOT', location=(0, 0, 5),
                     rotation=(math.radians(45), 0, 0), energy=50.0,
                     spot_size=math.radians(60), spot_blend=0.5)
    params = lights.convert_light(export_ctx, obj)
    assert params['type'] == 'spot'
    assert params['cutoff_angle'] == pytest.approx(30.0)
    expected_beam = math.degrees(
        math.acos(0.5 + 0.5 * math.cos(math.radians(30))))
    assert params['beam_width'] == pytest.approx(expected_beam, abs=1e-4)
    intensity = 50.0 / (4.0 * math.pi)
    assert params['intensity']['value'] == pytest.approx([intensity] * 3)
    # Mitsuba spots emit along the +Z axis of their to_world transform
    np.testing.assert_allclose(to_world_z_axis(params),
                               emitted_direction(export_ctx, obj),
                               atol=1e-6)

    import mitsuba as mi
    assert mi.load_dict(params) is not None


def test_sun_light(fresh_scene, export_ctx, lights):
    obj = make_light('SUN', rotation=(math.radians(30), math.radians(15), 0),
                     energy=2.5, color=(1.0, 0.9, 0.8))
    params = lights.convert_light(export_ctx, obj)
    assert params['type'] == 'directional'
    assert params['irradiance']['value'] == \
        pytest.approx([2.5, 2.5 * 0.9, 2.5 * 0.8])
    np.testing.assert_allclose(to_world_z_axis(params),
                               emitted_direction(export_ctx, obj),
                               atol=1e-6)

    import mitsuba as mi
    assert mi.load_dict(params) is not None


def test_sun_light_ignores_object_scale(fresh_scene, export_ctx, lights):
    # Mitsuba's directional emitter does not normalize the direction it
    # reads from to_world, so a scaled to_world would scale the irradiance
    obj = make_light('SUN', rotation=(math.radians(30), 0, 0), energy=2.5,
                     scale=(5.0, 2.0, 3.0))
    params = lights.convert_light(export_ctx, obj)
    matrix = np.array(params['to_world'].matrix)
    assert np.linalg.norm(matrix[:3, 2]) == pytest.approx(1.0)
    np.testing.assert_allclose(matrix[:3, 2],
                               emitted_direction(export_ctx, obj), atol=1e-6)


@pytest.mark.parametrize('shape,size,size_y,scale,expected_type,expected_area', [
    ('SQUARE', 2.0, None, (1, 1, 1), 'rectangle', 4.0),
    ('RECTANGLE', 2.0, 3.0, (2, 1, 1), 'rectangle', 12.0),
    ('DISK', 3.0, None, (1, 1, 1), 'disk', math.pi / 4.0 * 9.0),
    ('ELLIPSE', 2.0, 1.0, (1, 3, 1), 'disk', math.pi / 4.0 * 6.0),
])
def test_area_light(fresh_scene, export_ctx, lights, shape, size, size_y,
                    scale, expected_type, expected_area):
    data_props = {'shape': shape, 'size': size, 'energy': 90.0}
    if size_y is not None:
        data_props['size_y'] = size_y
    obj = make_light('AREA', scale=scale, **data_props)
    params = lights.convert_light(export_ctx, obj)
    assert params['type'] == expected_type
    assert params['flip_normals'] is True
    assert params['bsdf'] == {
        'type' : 'diffuse',
        'reflectance' : {
            'type' : 'rgb',
            'value' : 0.0
        }
    }


    radiance = 90.0 / (math.pi * expected_area)
    assert params['emitter']['radiance']['value'] == \
        pytest.approx([radiance] * 3, rel=1e-5)
    # The to_world transform carries half the world-space dimensions
    matrix = np.array(params['to_world'].matrix)
    size_y = size if size_y is None else size_y
    assert np.linalg.norm(matrix[:3, 0]) == \
        pytest.approx(size / 2.0 * scale[0], rel=1e-5)
    assert np.linalg.norm(matrix[:3, 1]) == \
        pytest.approx(size_y / 2.0 * scale[1], rel=1e-5)

    import mitsuba as mi
    assert mi.load_dict(params) is not None


def test_area_light_spread_warns(fresh_scene, export_ctx, lights,
                                 log_capture):
    obj = make_light('AREA', shape='SQUARE', size=1.0, energy=10.0,
                     spread=math.radians(90))
    params = lights.convert_light(export_ctx, obj)
    assert params['type'] == 'rectangle'
    assert any(level == 'WARN' and 'spread' in msg
               for level, msg in log_capture)


def test_degenerate_area_light_raises(fresh_scene, export_ctx, lights):
    obj = make_light('AREA', shape='SQUARE', size=0.0, energy=10.0)
    with pytest.raises(lights.ConversionError):
        lights.convert_light(export_ctx, obj)


def test_export_light_never_raises(export_ctx, lights, log_capture):
    fake_data = types.SimpleNamespace(type='LASER')
    fake_obj = types.SimpleNamespace(data=fake_data, name_full='Fake',
                                     matrix_world=Matrix())
    fake_instance = types.SimpleNamespace(object=fake_obj,
                                          matrix_world=Matrix())
    lights.export_light(export_ctx, fake_instance)
    assert list(export_ctx.scene_data.keys()) == ['type']
    assert any(level == 'WARN' for level, _ in log_capture)


def test_export_light_with_ids(fresh_scene, export_ctx, lights):
    obj = make_light('POINT', name='Key', energy=10.0)
    export_ctx.export_ids = True
    instance = types.SimpleNamespace(object=obj,
                                     matrix_world=obj.matrix_world)
    lights.export_light(export_ctx, instance)
    assert export_ctx.data_get('emit-Key') is not None


def test_spot_blend_inverse(lights):
    spot_size = math.radians(70)
    for blend in (0.0, 0.25, 0.5, 0.75, 1.0):
        beam = lights.spot_beam_width(spot_size, blend)
        assert lights.spot_blend(spot_size, beam) == \
            pytest.approx(blend, abs=1e-6)


def test_power_conversions_inverse(lights):
    assert lights.intensity_to_power(lights.power_to_intensity(42.0)) == \
        pytest.approx(42.0)
    assert lights.radiance_to_power(
        lights.power_to_radiance(42.0, 3.5), 3.5) == pytest.approx(42.0)
