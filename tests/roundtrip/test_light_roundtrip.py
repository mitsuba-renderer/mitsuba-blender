"""Numeric round-trip tests for the light radiometry, both directions."""

import importlib
import math

import bpy
import numpy as np
import pytest
from bpy_extras.io_utils import axis_conversion
from mathutils import Matrix, Vector

AXIS_MAT = axis_conversion(to_forward='-Z', to_up='Y').to_4x4()


@pytest.fixture(scope='session')
def export_lights(mi_addon):
    return importlib.import_module(f'{mi_addon}.convert.export.lights')


@pytest.fixture(scope='session')
def import_lights(mi_addon):
    return importlib.import_module(f'{mi_addon}.convert.importer.lights')


@pytest.fixture
def export_ctx(mi_addon, tmp_path):
    import mitsuba as mi
    mi.set_variant('scalar_rgb')
    module = importlib.import_module(f'{mi_addon}.io.exporter.export_context')
    ctx = module.ExportContext()
    ctx.directory = str(tmp_path)
    ctx.axis_mat = AXIS_MAT.copy()
    return ctx


def parse_scene_dict(scene_dict):
    """Parse a Mitsuba scene dict and return its parser state."""
    import mitsuba as mi
    config = mi.parser.ParserConfig(mi.variant())
    config.merge_meshes = False
    state = mi.parser.parse_dict(config, scene_dict)
    mi.parser.transform_all(config, state)
    return state


def collect_props(state, object_type):
    """The properties of all nodes of a given type, found by walking the
    reference graph from the root."""
    from mitsuba import Properties
    found = []
    stack = [state.root]
    while stack:
        node = stack.pop()
        for _, value in node.props.items():
            if isinstance(value, Properties.ResolvedReference):
                child = state.nodes[value.index()]
                stack.append(child)
                # Skip container plugins introduced by the parser
                if child.type == object_type \
                        and child.props.plugin_name() != 'merge':
                    found.append(child.props)
    return found


@pytest.fixture
def make_mi_context(mi_addon, tmp_path):
    common = importlib.import_module(f'{mi_addon}.io.importer.common')

    def _make(state):
        return common.MitsubaSceneImportContext(
            bpy.context, bpy.context.scene, bpy.context.collection,
            str(tmp_path / 'scene.xml'), state, AXIS_MAT.copy())

    return _make


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


def roundtrip_emitter(export_lights, import_lights, export_ctx,
                      make_mi_context, obj):
    """Export a Blender light and feed it back through the importer."""
    from mitsuba import ObjectType
    params = export_lights.convert_light(export_ctx, obj)
    state = parse_scene_dict({'type': 'scene', 'light': params})
    mi_context = make_mi_context(state)
    emitters = collect_props(state, ObjectType.Emitter)
    assert len(emitters) == 1
    if params['type'] in ('rectangle', 'disk', 'sphere'):
        shapes = collect_props(state, ObjectType.Shape)
        assert len(shapes) == 1
        result = import_lights.mi_area_emitter_to_bl_light(
            mi_context, emitters[0], shapes[0])
    else:
        result = import_lights.mi_emitter_to_bl_light(mi_context,
                                                      emitters[0])
    assert result is not None
    return result


def minus_z(matrix):
    direction = matrix.to_3x3() @ Vector((0.0, 0.0, -1.0))
    return np.array(direction.normalized())


def test_point_roundtrip(fresh_scene, export_ctx, export_lights,
                         import_lights, make_mi_context):
    obj = make_light('POINT', location=(1, 2, 3), energy=100.0,
                     color=(1.0, 0.5, 0.25))
    bl_light, matrix = roundtrip_emitter(export_lights, import_lights,
                                         export_ctx, make_mi_context, obj)
    assert bl_light.type == 'POINT'
    assert bl_light.energy == pytest.approx(100.0, rel=1e-4)
    assert tuple(bl_light.color) == pytest.approx((1.0, 0.5, 0.25),
                                                  rel=1e-4)
    assert list(matrix.to_translation()) == pytest.approx([1, 2, 3],
                                                          abs=1e-5)


def test_dim_point_light_keeps_radiometry(fresh_scene, export_ctx,
                                          export_lights, import_lights,
                                          make_mi_context):
    # A dim light imports with a different energy/color split, but the
    # product (the radiant intensity) must be preserved
    obj = make_light('POINT', energy=1.0, color=(0.8, 0.6, 0.4))
    bl_light, _ = roundtrip_emitter(export_lights, import_lights,
                                    export_ctx, make_mi_context, obj)
    original = [1.0 / (4 * math.pi) * c for c in (0.8, 0.6, 0.4)]
    imported = [bl_light.energy / (4 * math.pi) * c for c in bl_light.color]
    assert imported == pytest.approx(original, rel=1e-4)


def test_point_radius_roundtrip(fresh_scene, export_ctx, export_lights,
                                import_lights, make_mi_context):
    obj = make_light('POINT', location=(0, 1, 2), energy=60.0,
                     shadow_soft_size=0.5)
    bl_light, matrix = roundtrip_emitter(export_lights, import_lights,
                                         export_ctx, make_mi_context, obj)
    assert bl_light.type == 'POINT'
    assert bl_light.shadow_soft_size == pytest.approx(0.5, rel=1e-5)
    assert bl_light.energy == pytest.approx(60.0, rel=1e-4)
    assert list(matrix.to_translation()) == pytest.approx([0, 1, 2],
                                                          abs=1e-5)


def test_spot_roundtrip(fresh_scene, export_ctx, export_lights,
                        import_lights, make_mi_context):
    obj = make_light('SPOT', location=(2, -1, 4),
                     rotation=(0.4, 0.2, 0.1), energy=80.0,
                     spot_size=math.radians(65), spot_blend=0.3)
    bl_light, matrix = roundtrip_emitter(export_lights, import_lights,
                                         export_ctx, make_mi_context, obj)
    assert bl_light.type == 'SPOT'
    assert bl_light.energy == pytest.approx(80.0, rel=1e-4)
    assert bl_light.spot_size == pytest.approx(math.radians(65), rel=1e-4)
    assert bl_light.spot_blend == pytest.approx(0.3, abs=1e-4)
    np.testing.assert_allclose(minus_z(matrix),
                               minus_z(obj.matrix_world), atol=1e-5)
    assert list(matrix.to_translation()) == pytest.approx([2, -1, 4],
                                                          abs=1e-5)


def test_sun_roundtrip(fresh_scene, export_ctx, export_lights,
                       import_lights, make_mi_context):
    obj = make_light('SUN', rotation=(0.5, -0.3, 0.2), energy=3.0,
                     color=(1.0, 0.9, 0.8), angle=0.05)
    bl_light, matrix = roundtrip_emitter(export_lights, import_lights,
                                         export_ctx, make_mi_context, obj)
    assert bl_light.type == 'SUN'
    # The energy of a sun light is its irradiance and survives unchanged
    assert bl_light.energy == pytest.approx(3.0, rel=1e-4)
    assert tuple(bl_light.color) == pytest.approx((1.0, 0.9, 0.8), rel=1e-4)
    assert bl_light.angle == 0.0
    np.testing.assert_allclose(minus_z(matrix),
                               minus_z(obj.matrix_world), atol=1e-5)


@pytest.mark.parametrize('shape,size,size_y,scale,expected_shape', [
    ('RECTANGLE', 2.0, 3.0, (2, 1, 1), 'RECTANGLE'),
    ('SQUARE', 1.5, None, (1, 1, 1), 'RECTANGLE'),
    ('DISK', 3.0, None, (1, 1, 1), 'DISK'),
    ('ELLIPSE', 2.0, 1.0, (1, 1, 1), 'ELLIPSE'),
])
def test_area_roundtrip(fresh_scene, export_ctx, export_lights,
                        import_lights, make_mi_context, shape, size, size_y,
                        scale, expected_shape):
    data_props = {'shape': shape, 'size': size, 'energy': 45.0}
    if size_y is not None:
        data_props['size_y'] = size_y
    obj = make_light('AREA', location=(0, 0, 3), rotation=(0.3, 0.1, 0.7),
                     scale=scale, **data_props)
    bl_light, matrix = roundtrip_emitter(export_lights, import_lights,
                                         export_ctx, make_mi_context, obj)
    assert bl_light.type == 'AREA'
    assert bl_light.shape == expected_shape
    assert bl_light.energy == pytest.approx(45.0, rel=1e-4)
    # The effective world-space dimensions must match the original
    size_y = size if size_y is None else size_y
    imported_scale = matrix.to_scale()
    assert bl_light.size * imported_scale.x == \
        pytest.approx(size * scale[0], rel=1e-4)
    if expected_shape in ('RECTANGLE', 'ELLIPSE'):
        assert bl_light.size_y * imported_scale.y == \
            pytest.approx(size_y * scale[1], rel=1e-4)
    np.testing.assert_allclose(minus_z(matrix),
                               minus_z(obj.matrix_world), atol=1e-5)
    assert list(matrix.to_translation()) == pytest.approx([0, 0, 3],
                                                          abs=1e-5)


def test_foreign_rectangle_emitter_orientation(fresh_scene, export_ctx,
                                               import_lights,
                                               make_mi_context):
    # A Mitsuba rectangle without flipped normals emits along its +Z
    # axis; the imported Blender area light must emit the same way
    from mitsuba import ObjectType
    state = parse_scene_dict({
        'type': 'scene',
        'light': {
            'type': 'rectangle',
            'emitter': {'type': 'area',
                        'radiance': {'type': 'rgb', 'value': [5, 5, 5]}},
        },
    })
    mi_context = make_mi_context(state)
    emitter = collect_props(state, ObjectType.Emitter)[0]
    shape = collect_props(state, ObjectType.Shape)[0]
    bl_light, matrix = import_lights.mi_area_emitter_to_bl_light(
        mi_context, emitter, shape)
    assert bl_light.type == 'AREA'
    # radiance 5 over the 2x2 rectangle: P = 5 * pi * 4
    assert bl_light.energy == pytest.approx(5 * math.pi * 4, rel=1e-4)
    expected = np.array(AXIS_MAT.inverted().to_3x3() @ Vector((0, 0, 1)))
    np.testing.assert_allclose(minus_z(matrix), expected, atol=1e-6)


def test_unsupported_emitter_returns_none(fresh_scene, import_lights,
                                          make_mi_context):
    from mitsuba import ObjectType
    state = parse_scene_dict({
        'type': 'scene',
        'light': {'type': 'projector'},
    })
    mi_context = make_mi_context(state)
    logs = []
    mi_context.log = lambda msg, level='INFO': logs.append((level, msg))
    emitter = collect_props(state, ObjectType.Emitter)[0]
    assert import_lights.mi_emitter_to_bl_light(mi_context, emitter) is None
    assert any(level == 'WARN' for level, _ in logs)


def test_import_spot_defaults(fresh_scene, import_lights, make_mi_context):
    # Mitsuba's spot defaults: cutoff_angle 20 deg, beam_width 3/4 of it
    from mitsuba import ObjectType
    state = parse_scene_dict({
        'type': 'scene',
        'light': {'type': 'spot'},
    })
    mi_context = make_mi_context(state)
    emitter = collect_props(state, ObjectType.Emitter)[0]
    bl_light, _ = import_lights.mi_emitter_to_bl_light(mi_context, emitter)
    assert bl_light.spot_size == pytest.approx(math.radians(40), rel=1e-5)
    expected_blend = import_lights.spot_blend(
        math.radians(40), math.radians(15))
    assert bl_light.spot_blend == pytest.approx(expected_blend, rel=1e-4)
