"""Round-trip and import tests for world/environment emitters."""

import importlib
import os

import bpy
import numpy as np
import pytest
from bpy_extras.io_utils import axis_conversion
from mathutils import Vector

AXIS_MAT = axis_conversion(to_forward='-Z', to_up='Y').to_4x4()


@pytest.fixture(scope='session')
def export_world(mi_addon):
    return importlib.import_module(f'{mi_addon}.convert.export.world')


@pytest.fixture(scope='session')
def import_world(mi_addon):
    return importlib.import_module(f'{mi_addon}.convert.importer.world')


@pytest.fixture
def export_ctx(mi_addon, tmp_path):
    import mitsuba as mi
    mi.set_variant('scalar_rgb')
    module = importlib.import_module(f'{mi_addon}.io.exporter.export_context')
    ctx = module.ExportContext()
    ctx.directory = str(tmp_path)
    ctx.axis_mat = AXIS_MAT.copy()
    return ctx


@pytest.fixture
def make_mi_context(mi_addon, tmp_path):
    common = importlib.import_module(f'{mi_addon}.io.importer.common')

    def _make(state):
        return common.MitsubaSceneImportContext(
            bpy.context.scene, bpy.context.collection,
            str(tmp_path / 'scene.xml'), state, AXIS_MAT.copy())

    return _make


def emitter_props(scene_dict):
    """Parse a scene dict and return (state, props of the only emitter)."""
    import mitsuba as mi
    from mitsuba import ObjectType
    config = mi.parser.ParserConfig(mi.variant())
    state = mi.parser.parse_dict(config, scene_dict)
    mi.parser.transform_all(config, state)
    emitters = [state.nodes[i].props for i in range(len(state.nodes))
                if state.nodes[i].type == ObjectType.Emitter]
    assert len(emitters) == 1
    return state, emitters[0]


def find_nodes(bl_world, bl_idname):
    return [node for node in bl_world.node_tree.nodes
            if node.bl_idname == bl_idname]


def background_node(bl_world):
    nodes = find_nodes(bl_world, 'ShaderNodeBackground')
    assert len(nodes) == 1
    return nodes[0]


def make_env_world(export_world_module, tmp_path, rotation=None,
                   strength=1.0):
    image = bpy.data.images.new('env', 8, 4, float_buffer=True)
    image.filepath_raw = str(tmp_path / 'env.exr')
    image.file_format = 'OPEN_EXR'
    image.save()
    b_world = bpy.data.worlds.new('EnvWorld')
    b_world.use_nodes = True
    tree = b_world.node_tree
    background = tree.nodes['Background']
    background.inputs['Strength'].default_value = strength
    environment = tree.nodes.new('ShaderNodeTexEnvironment')
    environment.image = image
    tree.links.new(environment.outputs['Color'],
                   background.inputs['Color'])
    if rotation is not None:
        mapping = tree.nodes.new('ShaderNodeMapping')
        mapping.vector_type = 'TEXTURE'
        mapping.inputs['Rotation'].default_value = rotation
        coordinates = tree.nodes.new('ShaderNodeTexCoord')
        tree.links.new(coordinates.outputs['Generated'],
                       mapping.inputs['Vector'])
        tree.links.new(mapping.outputs['Vector'],
                       environment.inputs['Vector'])
    return b_world


def test_constant_roundtrip(fresh_scene, export_ctx, export_world,
                            import_world, make_mi_context):
    b_world = bpy.data.worlds.new('Const')
    b_world.use_nodes = True
    background = b_world.node_tree.nodes['Background']
    background.inputs['Color'].default_value = (0.2, 0.4, 0.6, 1.0)
    background.inputs['Strength'].default_value = 2.0

    params = export_world.convert_world(export_ctx, b_world)
    state, mi_props = emitter_props({'type': 'scene', 'world': params})
    bl_world = import_world.mi_emitter_to_bl_world(make_mi_context(state),
                                                   mi_props)
    imported = background_node(bl_world)
    color = list(imported.inputs['Color'].default_value)[:3]
    strength = imported.inputs['Strength'].default_value
    # The color/strength split may differ; the radiance must not
    radiance = [c * strength for c in color]
    assert radiance == pytest.approx([0.4, 0.8, 1.2], rel=1e-4)

    # Exporting the imported world reproduces the radiance
    params2 = export_world.convert_world(export_ctx, bl_world)
    assert params2['radiance']['value'] == \
        pytest.approx([0.4, 0.8, 1.2], rel=1e-4)


def test_constant_float_radiance_import(fresh_scene, import_world,
                                        make_mi_context):
    state, mi_props = emitter_props({
        'type': 'scene',
        'world': {'type': 'constant', 'radiance': 5.0},
    })
    bl_world = import_world.mi_emitter_to_bl_world(make_mi_context(state),
                                                   mi_props)
    imported = background_node(bl_world)
    assert list(imported.inputs['Color'].default_value)[:3] == \
        pytest.approx([1.0] * 3)
    assert imported.inputs['Strength'].default_value == pytest.approx(5.0)


def test_envmap_roundtrip_with_rotation(fresh_scene, export_ctx,
                                        export_world, import_world,
                                        make_mi_context, tmp_path):
    rotation = (0.3, 0.0, 1.1)
    b_world = make_env_world(export_world, tmp_path, rotation=rotation,
                             strength=1.5)
    params = export_world.convert_world(export_ctx, b_world)
    state, mi_props = emitter_props({'type': 'scene', 'world': params})
    bl_world = import_world.mi_emitter_to_bl_world(make_mi_context(state),
                                                   mi_props)

    imported = background_node(bl_world)
    assert imported.inputs['Strength'].default_value == pytest.approx(1.5)
    environment = find_nodes(bl_world, 'ShaderNodeTexEnvironment')
    assert len(environment) == 1
    assert environment[0].image is not None
    mapping = find_nodes(bl_world, 'ShaderNodeMapping')
    assert len(mapping) == 1
    assert mapping[0].vector_type == 'TEXTURE'
    assert tuple(mapping[0].inputs['Rotation'].default_value) == \
        pytest.approx(rotation, abs=1e-5)

    # A second export reproduces the same transform and scale
    params2 = export_world.convert_world(export_ctx, bl_world)
    assert params2['scale'] == pytest.approx(1.5)
    np.testing.assert_allclose(np.array(params2['to_world'].matrix),
                               np.array(params['to_world'].matrix),
                               atol=1e-5)


def test_envmap_import_without_rotation(fresh_scene, export_ctx,
                                        export_world, import_world,
                                        make_mi_context, tmp_path):
    b_world = make_env_world(export_world, tmp_path)
    params = export_world.convert_world(export_ctx, b_world)
    state, mi_props = emitter_props({'type': 'scene', 'world': params})
    bl_world = import_world.mi_emitter_to_bl_world(make_mi_context(state),
                                                   mi_props)
    assert len(find_nodes(bl_world, 'ShaderNodeTexEnvironment')) == 1
    # An identity transform must not create a mapping node
    assert len(find_nodes(bl_world, 'ShaderNodeMapping')) == 0


def test_envmap_missing_file_yields_error_world(fresh_scene, import_world,
                                                make_mi_context):
    state, mi_props = emitter_props({
        'type': 'scene',
        'world': {'type': 'envmap', 'filename': 'missing.exr'},
    })
    mi_context = make_mi_context(state)
    logs = []
    mi_context.log = lambda msg, level='INFO': logs.append((level, msg))
    bl_world = import_world.mi_emitter_to_bl_world(mi_context, mi_props)
    imported = background_node(bl_world)
    assert tuple(imported.inputs['Color'].default_value) == \
        pytest.approx(import_world.ERROR_COLOR)
    assert any(level == 'WARN' for level, _ in logs)


def test_sunsky_imports_placeholder_with_warning(fresh_scene, import_world,
                                                 make_mi_context):
    state, mi_props = emitter_props({
        'type': 'scene',
        'world': {'type': 'sunsky'},
    })
    mi_context = make_mi_context(state)
    logs = []
    mi_context.log = lambda msg, level='INFO': logs.append((level, msg))
    assert import_world.should_convert_mi_emitter_to_bl_world(mi_props)
    bl_world = import_world.mi_emitter_to_bl_world(mi_context, mi_props)
    assert background_node(bl_world) is not None
    assert any(level == 'WARN' and 'sunsky' in msg for level, msg in logs)


def test_should_convert_dispatch(fresh_scene, import_world,
                                 make_mi_context):
    state, mi_props = emitter_props({
        'type': 'scene',
        'world': {'type': 'point'},
    })
    assert not import_world.should_convert_mi_emitter_to_bl_world(mi_props)


def test_default_world_roundtrips_to_nothing(fresh_scene, export_ctx,
                                             export_world, import_world):
    # The default world created on import is recognized and skipped by
    # the exporter's ignore_background option
    bl_world = import_world.create_default_bl_world()
    assert export_world.convert_world(export_ctx, bl_world,
                                      ignore_background=True) is None


##############################
##  Baked (procedural) world  ##
##############################

# Directions to look along, asymmetric and away from the poles so that an
# azimuth error in the baked map shows up as well as an elevation one
SENSOR_DIRECTIONS = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0),
                     (0.0, -1.0, 0.0), (1.0, 1.0, 0.5), (-1.0, 0.7, 0.3)]
SENSOR_RESOLUTION = 32
SENSOR_FOV = 60.0
BAKE_RESOLUTION = 256


def make_procedural_world():
    """A world whose color encodes the direction it is looked at along, so
    that any rotation of the map it bakes to changes every rendered pixel.
    Being procedural, it cannot be translated and has to be baked."""
    b_world = bpy.data.worlds.new('Procedural')
    b_world.use_nodes = True
    tree = b_world.node_tree
    tree.nodes.clear()
    background = tree.nodes.new('ShaderNodeBackground')
    coordinates = tree.nodes.new('ShaderNodeTexCoord')
    separate = tree.nodes.new('ShaderNodeSeparateXYZ')
    tree.links.new(coordinates.outputs['Generated'], separate.inputs['Vector'])
    combine = tree.nodes.new('ShaderNodeCombineColor')
    for index, axis in enumerate('XYZ'):
        # The direction components run over [-1, 1], the channels over [0, 1]
        remap = tree.nodes.new('ShaderNodeMath')
        remap.operation = 'MULTIPLY_ADD'
        remap.inputs[1].default_value = 0.5
        remap.inputs[2].default_value = 0.5
        tree.links.new(separate.outputs[axis], remap.inputs[0])
        tree.links.new(remap.outputs['Value'], combine.inputs[index])
    tree.links.new(combine.outputs['Color'], background.inputs['Color'])
    output = tree.nodes.new('ShaderNodeOutputWorld')
    tree.links.new(background.outputs['Background'], output.inputs['Surface'])
    return b_world


def sensor_up(direction):
    up = Vector((0.0, 0.0, 1.0))
    if abs(direction.dot(up)) > 0.95:
        up = Vector((0.0, 1.0, 0.0))
    return up


def render_cycles(b_scene, direction, filepath):
    """The world of ``b_scene`` as a camera at the origin looking along
    ``direction`` sees it."""
    import mitsuba as mi
    b_scene.camera.rotation_euler = \
        direction.to_track_quat('-Z', 'Y').to_euler()
    b_scene.render.filepath = filepath
    bpy.ops.render.render(write_still=True)
    return np.array(mi.Bitmap(filepath).convert(mi.Bitmap.PixelFormat.RGB,
                                                mi.Struct.Type.Float32, False))


def render_mitsuba(params, directory, direction):
    """The emitter ``params`` as a sensor pointed the same way sees it. The
    emitter's to_world carries the exporter's axis conversion, so the
    direction has to be expressed in Mitsuba's frame as well."""
    import mitsuba as mi
    basis = AXIS_MAT.to_3x3()
    direction = basis @ direction
    emitter = dict(params,
                   filename=os.path.join(directory, params['filename']))
    scene = mi.load_dict({
        'type': 'scene',
        'integrator': {'type': 'path'},
        'world': emitter,
        'sensor': {
            'type': 'perspective',
            'fov': SENSOR_FOV,
            'fov_axis': 'x',
            'to_world': mi.ScalarTransform4f().look_at(
                origin=[0, 0, 0], target=list(direction),
                up=list(basis @ sensor_up(basis.inverted() @ direction))),
            'film': {'type': 'hdrfilm', 'width': SENSOR_RESOLUTION,
                     'height': SENSOR_RESOLUTION, 'pixel_format': 'rgb',
                     'rfilter': {'type': 'box'}},
            'sampler': {'type': 'independent', 'sample_count': 16},
        },
    })
    return np.array(mi.render(scene, spp=16))


def test_baked_world_renders_like_cycles(fresh_scene, export_ctx,
                                         export_world, tmp_path):
    """A world that has to be baked lights a Mitsuba scene exactly as Cycles
    renders the original, which pins the orientation of the baked map."""
    import math
    b_scene = fresh_scene
    # Only the world may contribute: the startup scene's cube encloses the
    # sensor at the origin and would be all the render sees
    for b_object in list(b_scene.objects):
        bpy.data.objects.remove(b_object, do_unlink=True)
    b_scene.world = make_procedural_world()
    b_scene.render.engine = 'CYCLES'
    b_scene.cycles.samples = 1
    b_scene.cycles.use_denoising = False
    b_scene.render.resolution_x = SENSOR_RESOLUTION
    b_scene.render.resolution_y = SENSOR_RESOLUTION
    b_scene.render.resolution_percentage = 100
    b_scene.render.film_transparent = False
    settings = b_scene.render.image_settings
    settings.file_format = 'OPEN_EXR'
    settings.color_mode = 'RGB'
    settings.color_depth = '32'
    b_scene.view_settings.view_transform = 'Standard'
    b_scene.view_settings.look = 'None'

    b_camera_data = bpy.data.cameras.new('sensor')
    b_camera_data.lens_unit = 'FOV'
    b_camera_data.angle = math.radians(SENSOR_FOV)
    b_camera = bpy.data.objects.new('sensor', b_camera_data)
    b_camera.location = (0.0, 0.0, 0.0)
    b_scene.collection.objects.link(b_camera)
    b_scene.camera = b_camera

    export_ctx.strict = False
    export_ctx.bake_world_resolution = BAKE_RESOLUTION
    export_world.export_world(export_ctx, b_scene.world)
    params = next(value for key, value in export_ctx.scene_data.items()
                  if key != 'type')
    assert params['type'] == 'envmap'

    for direction in SENSOR_DIRECTIONS:
        direction = Vector(direction).normalized()
        reference = render_cycles(b_scene, direction,
                                  str(tmp_path / 'cycles.exr'))
        image = render_mitsuba(params, str(tmp_path), direction)
        error = float(np.abs(image - reference).mean())
        assert error < 0.01, \
            f'looking along {tuple(direction)}, the baked world differs ' \
            f'from Cycles by {error:.4f} on average'
