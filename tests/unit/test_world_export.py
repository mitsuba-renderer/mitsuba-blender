"""Unit tests for the Blender world to Mitsuba emitter converter."""

import importlib
import math
import os

import bpy
import numpy as np
import pytest
from bpy_extras.io_utils import axis_conversion
from mathutils import Matrix


@pytest.fixture(scope='session')
def world(mi_addon):
    return importlib.import_module(f'{mi_addon}.convert.export.world')


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


def make_world(color=None, strength=None, name='TestWorld'):
    b_world = bpy.data.worlds.new(name)
    b_world.use_nodes = True
    background = b_world.node_tree.nodes['Background']
    if color is not None:
        background.inputs['Color'].default_value = color
    if strength is not None:
        background.inputs['Strength'].default_value = strength
    return b_world


def make_env_image(tmp_path, name='env'):
    image = bpy.data.images.new(name, 8, 4, float_buffer=True)
    image.filepath_raw = str(tmp_path / f'{name}.exr')
    image.file_format = 'OPEN_EXR'
    image.save()
    return image


def make_env_world(tmp_path, rotation=None, vector_type='POINT',
                   strength=1.0):
    b_world = make_world(strength=strength, name='EnvWorld')
    tree = b_world.node_tree
    background = tree.nodes['Background']
    environment = tree.nodes.new('ShaderNodeTexEnvironment')
    environment.image = make_env_image(tmp_path)
    tree.links.new(environment.outputs['Color'],
                   background.inputs['Color'])
    if rotation is not None:
        mapping = tree.nodes.new('ShaderNodeMapping')
        mapping.vector_type = vector_type
        mapping.inputs['Rotation'].default_value = rotation
        coordinates = tree.nodes.new('ShaderNodeTexCoord')
        tree.links.new(coordinates.outputs['Generated'],
                       mapping.inputs['Vector'])
        tree.links.new(mapping.outputs['Vector'],
                       environment.inputs['Vector'])
    return b_world


def load_with_resolver(params, directory):
    """Load a Mitsuba dict whose file references are relative to a
    directory."""
    import mitsuba as mi
    fr = mi.file_resolver()
    paths = list(fr)
    fr.prepend(str(directory))
    try:
        return mi.load_dict(params)
    finally:
        fr.clear()
        for path in paths:
            fr.append(path)


def test_constant_background(fresh_scene, export_ctx, world):
    b_world = make_world(color=(0.2, 0.4, 0.6, 1.0), strength=2.0)
    params = world.convert_world(export_ctx, b_world)
    assert params['type'] == 'constant'
    assert params['radiance']['value'] == \
        pytest.approx([0.4, 0.8, 1.2], rel=1e-5)

    import mitsuba as mi
    assert mi.load_dict(params) is not None


def test_default_background_ignored(fresh_scene, export_ctx, world):
    b_world = bpy.context.scene.world
    assert world.convert_world(export_ctx, b_world,
                               ignore_background=True) is None
    params = world.convert_world(export_ctx, b_world,
                                 ignore_background=False)
    assert params['type'] == 'constant'
    assert params['radiance']['value'] == \
        pytest.approx(world.DEFAULT_BACKGROUND)


def test_zero_strength_skipped(fresh_scene, export_ctx, world):
    b_world = make_world(color=(1.0, 1.0, 1.0, 1.0), strength=0.0)
    assert world.convert_world(export_ctx, b_world) is None


def test_zero_radiance_skipped(fresh_scene, export_ctx, world):
    b_world = make_world(color=(0.0, 0.0, 0.0, 1.0), strength=1.0)
    assert world.convert_world(export_ctx, b_world) is None


def test_rgb_node_color_folds(fresh_scene, export_ctx, world):
    # The RGB node value lives on its output socket, not node.color
    # (PR #153)
    b_world = make_world(strength=0.5)
    tree = b_world.node_tree
    rgb = tree.nodes.new('ShaderNodeRGB')
    rgb.outputs['Color'].default_value = (1.0, 0.0, 0.2, 1.0)
    tree.links.new(rgb.outputs['Color'],
                   tree.nodes['Background'].inputs['Color'])
    params = world.convert_world(export_ctx, b_world)
    assert params['radiance']['value'] == \
        pytest.approx([0.5, 0.0, 0.1], rel=1e-5)


def test_world_without_nodes(fresh_scene, export_ctx, world):
    b_world = bpy.data.worlds.new('Plain')
    b_world.use_nodes = False
    b_world.color = (0.1, 0.2, 0.3)
    params = world.convert_world(export_ctx, b_world)
    assert params['type'] == 'constant'
    assert params['radiance']['value'] == \
        pytest.approx([0.1, 0.2, 0.3], rel=1e-5)


def test_unlinked_surface(fresh_scene, export_ctx, world):
    b_world = make_world()
    tree = b_world.node_tree
    for link in list(tree.links):
        tree.links.remove(link)
    assert world.convert_world(export_ctx, b_world) is None


def test_no_world(export_ctx, world, log_capture):
    assert world.convert_world(export_ctx, None) is None


def test_unsupported_surface_node(fresh_scene, export_ctx, world,
                                  log_capture):
    b_world = make_world()
    tree = b_world.node_tree
    mix = tree.nodes.new('ShaderNodeMixShader')
    output = tree.nodes['World Output']
    tree.links.new(mix.outputs['Shader'], output.inputs['Surface'])
    with pytest.raises(world.ConversionError):
        world.convert_world(export_ctx, b_world)
    # The export entry point swallows the error with a warning
    world.export_world(export_ctx, b_world)
    assert list(export_ctx.scene_data.keys()) == ['type']
    assert any(level == 'WARN' for level, _ in log_capture)


def test_envmap(fresh_scene, export_ctx, world, tmp_path):
    b_world = make_env_world(tmp_path, strength=1.5)
    params = world.convert_world(export_ctx, b_world)
    assert params['type'] == 'envmap'
    assert params['scale'] == pytest.approx(1.5)
    assert os.path.isfile(os.path.join(str(tmp_path), params['filename']))
    # Without a mapping node, only the equirectangular convention change
    expected = np.array(export_ctx.axis_mat @ world.ENVMAP_COORDINATE_MAT)
    np.testing.assert_allclose(np.array(params['to_world'].matrix),
                               expected, atol=1e-6)
    assert load_with_resolver(params, tmp_path) is not None


@pytest.mark.parametrize('vector_type,sign', [('POINT', -1.0),
                                              ('TEXTURE', 1.0)])
def test_envmap_rotation(fresh_scene, export_ctx, world, tmp_path,
                         vector_type, sign):
    theta = math.radians(75)
    b_world = make_env_world(tmp_path, rotation=(0.0, 0.0, theta),
                             vector_type=vector_type)
    params = world.convert_world(export_ctx, b_world)
    # Point mappings rotate the lookup direction, texture mappings rotate
    # the environment itself (the inverse)
    expected = np.array(export_ctx.axis_mat
                        @ Matrix.Rotation(sign * theta, 4, 'Z')
                        @ world.ENVMAP_COORDINATE_MAT)
    np.testing.assert_allclose(np.array(params['to_world'].matrix),
                               expected, atol=1e-6)


def test_envmap_bad_mapping_source(fresh_scene, export_ctx, world,
                                   tmp_path):
    b_world = make_env_world(tmp_path)
    tree = b_world.node_tree
    environment = tree.nodes['Environment Texture']
    mapping = tree.nodes.new('ShaderNodeMapping')
    # A mapping node without generated texture coordinates is rejected
    tree.links.new(mapping.outputs['Vector'],
                   environment.inputs['Vector'])
    with pytest.raises(world.ConversionError):
        world.convert_world(export_ctx, b_world)


def test_export_world_adds_entry(fresh_scene, export_ctx, world):
    b_world = make_world(color=(0.3, 0.3, 0.3, 1.0), strength=1.0)
    export_ctx.export_ids = True
    world.export_world(export_ctx, b_world)
    assert export_ctx.data_get('World')['type'] == 'constant'
