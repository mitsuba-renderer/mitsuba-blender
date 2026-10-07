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


def test_default_color_at_other_strength_is_kept(fresh_scene, export_ctx,
                                                 world):
    # Only an untouched world is the default one; a color/strength pair that
    # merely multiplies out to the default gray must still be exported
    gray = world.DEFAULT_BACKGROUND[0]
    for color, strength in ((2.0 * gray, 0.5), (gray / 4.0, 4.0),
                            (1.0, gray), (gray, 2.0)):
        b_world = make_world(color=(color, color, color, 1.0),
                             strength=strength)
        params = world.convert_world(export_ctx, b_world,
                                     ignore_background=True)
        assert params is not None, \
            f'color {color} at strength {strength} was dropped'
        assert params['radiance']['value'] == \
            pytest.approx([color * strength] * 3, rel=1e-5)


def test_zero_strength_skipped(fresh_scene, export_ctx, world):
    b_world = make_world(color=(1.0, 1.0, 1.0, 1.0), strength=0.0)
    assert world.convert_world(export_ctx, b_world) is None


def test_zero_radiance_skipped(fresh_scene, export_ctx, world):
    b_world = make_world(color=(0.0, 0.0, 0.0, 1.0), strength=1.0)
    assert world.convert_world(export_ctx, b_world) is None


def test_rgb_node_color(fresh_scene, export_ctx, world):
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
    if world.uses_nodes(b_world):
        # Blender 5 ignores use_nodes and the default Background node's
        # color is exported instead of the world color
        expected = list(b_world.node_tree.nodes['Background']
                        .inputs['Color'].default_value)[:3]
    else:
        expected = [0.1, 0.2, 0.3]
    params = world.convert_world(export_ctx, b_world)
    assert params['type'] == 'constant'
    assert params['radiance']['value'] == pytest.approx(expected, rel=1e-5)


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


def test_envmap_render_mode_keeps_hdr(fresh_scene, export_ctx, world,
                                      tmp_path):
    import mitsuba as mi
    # Render mode hands the pixels to Mitsuba in memory; values above 1 TODO: check if this is still true
    # must survive and no files may be written
    b_world = make_env_world(tmp_path)
    image = bpy.data.images['env']
    pixels = np.full(len(image.pixels), 5.0, dtype=np.float32)
    image.pixels.foreach_set(pixels)
    chk = np.empty(len(image.pixels), dtype=np.float32)
    image.pixels.foreach_get(chk)
    print('is_dirty:', image.is_dirty)
    print('buffer:', chk.min(), chk.max(), 'is_float:', image.is_float,
          'source:', image.source, 'has_data:', image.has_data)

    export_ctx.render = True
    params = world.convert_world(export_ctx, b_world)
    assert params['type'] == 'envmap'
    assert 'bitmap' not in params
    path = tmp_path / params['filename']
    assert path.suffix == '.exr'
    bmp = mi.Bitmap(str(path))
    assert np.max(np.array(bmp)) == pytest.approx(5.0)

    from test_texture_export import resolver_append
    with resolver_append(export_ctx.directory):
        assert mi.load_dict(params) is not None


def test_envmap_export_leaves_image_datablock_alone(fresh_scene, export_ctx,
                                                    world, tmp_path):
    # A TIFF source is converted through a temporary copy; the user's
    # Image datablock must keep its format
    source = bpy.data.images.new('tif-src', 8, 4)
    source.filepath_raw = str(tmp_path / 'source.tif')
    source.file_format = 'TIFF'
    source.save()
    image = bpy.data.images.load(str(tmp_path / 'source.tif'))
    assert image.file_format == 'TIFF'

    b_world = make_world(name='EnvWorld')
    tree = b_world.node_tree
    environment = tree.nodes.new('ShaderNodeTexEnvironment')
    environment.image = image
    tree.links.new(environment.outputs['Color'],
                   tree.nodes['Background'].inputs['Color'])

    params = world.convert_world(export_ctx, b_world)
    assert image.file_format == 'TIFF'
    assert os.path.isfile(os.path.join(str(tmp_path), params['filename']))


def make_pattern_image(tmp_path, name='pattern', width=64, height=32):
    """A float environment image whose red channel encodes u and green v, so
    that a bake of it can be compared to the original, orientation
    included."""
    image = bpy.data.images.new(name, width, height, float_buffer=True)
    # The color space has to be set before the pixels: changing it afterwards
    # drops the buffer
    image.colorspace_settings.name = 'Non-Color'
    u = (np.arange(width) + 0.5) / width
    v = (np.arange(height) + 0.5) / height
    pixels = np.ones((height, width, 4), dtype=np.float32)
    pixels[..., 0] = u[None, :]
    pixels[..., 1] = v[:, None]
    pixels[..., 2] = np.abs(u - 0.25)[None, :] < 1.0 / width
    image.pixels.foreach_set(pixels.ravel())
    image.filepath_raw = str(tmp_path / f'{name}.exr')
    image.file_format = 'OPEN_EXR'
    image.save()
    return image


def make_sky_world():
    """A world driven by a Sky Texture, which has no Mitsuba equivalent."""
    b_world = make_world(strength=1.0, name='SkyWorld')
    tree = b_world.node_tree
    sky = tree.nodes.new('ShaderNodeTexSky')
    tree.links.new(sky.outputs['Color'],
                   tree.nodes['Background'].inputs['Color'])
    return b_world


def make_mix_shader_world(name='MixWorld', colors=((0.0, 0.5, 0.0, 1.0),
                                                   (0.5, 0.0, 0.0, 1.0))):
    """A world whose surface is a Mix Shader of two Background nodes."""
    b_world = make_world(name=name)
    tree = b_world.node_tree
    mix = tree.nodes.new('ShaderNodeMixShader')
    for index, color in enumerate(colors, start=1):
        background = tree.nodes.new('ShaderNodeBackground')
        background.inputs['Color'].default_value = color
        tree.links.new(background.outputs['Background'], mix.inputs[index])
    tree.links.new(mix.outputs['Shader'],
                   tree.nodes['World Output'].inputs['Surface'])
    return b_world


def read_rgb(path):
    """An EXR file as a float (height, width, 3) array."""
    import mitsuba as mi
    return np.array(mi.Bitmap(path).convert(mi.Bitmap.PixelFormat.RGB,
                                            mi.Struct.Type.Float32, False))


def only_emitter(export_ctx):
    """The single plugin export_world added to the scene dict."""
    entries = [value for key, value in export_ctx.scene_data.items()
               if key != 'type']
    assert len(entries) == 1
    return entries[0]


@pytest.fixture
def bake_ctx(export_ctx):
    """An export context that bakes an untranslatable world, at a resolution
    small enough for a test."""
    export_ctx.strict = False
    export_ctx.bake_world_resolution = 32
    return export_ctx


@pytest.mark.parametrize('make_untranslatable_world',
                         [make_sky_world, make_mix_shader_world])
def test_untranslatable_world_is_baked(fresh_scene, bake_ctx, world,
                                       log_capture, tmp_path,
                                       make_untranslatable_world):
    b_world = make_untranslatable_world()
    with pytest.raises(world.ConversionError):
        world.convert_world(bake_ctx, b_world)

    world.export_world(bake_ctx, b_world)
    params = only_emitter(bake_ctx)
    assert params['type'] == 'envmap'
    # The bake holds the world's strength already
    assert params['scale'] == 1.0
    assert os.path.isfile(os.path.join(str(tmp_path), params['filename']))
    # A baked world is parametrized like a translated environment texture
    expected = np.array(bake_ctx.axis_mat @ world.ENVMAP_COORDINATE_MAT)
    np.testing.assert_allclose(np.array(params['to_world'].matrix), expected,
                               atol=1e-6)
    assert load_with_resolver(params, tmp_path) is not None
    assert any(level == 'INFO' and b_world.name in message
               for level, message in log_capture)


def test_baked_world_matches_the_source_environment(fresh_scene, bake_ctx,
                                                    world, tmp_path):
    # An environment texture that does not feed the Color input directly
    # cannot be translated, and the bake of it must reproduce it
    image = make_pattern_image(tmp_path)
    b_world = make_world(strength=1.0, name='IndirectEnvWorld')
    tree = b_world.node_tree
    environment = tree.nodes.new('ShaderNodeTexEnvironment')
    environment.image = image
    gamma = tree.nodes.new('ShaderNodeGamma')
    gamma.inputs['Gamma'].default_value = 1.0
    tree.links.new(environment.outputs['Color'], gamma.inputs['Color'])
    tree.links.new(gamma.outputs['Color'],
                   tree.nodes['Background'].inputs['Color'])
    with pytest.raises(world.ConversionError):
        world.convert_world(bake_ctx, b_world)

    world.export_world(bake_ctx, b_world)
    params = only_emitter(bake_ctx)
    baked = read_rgb(os.path.join(str(tmp_path), params['filename']))
    source = read_rgb(str(tmp_path / 'pattern.exr'))
    assert baked.shape == source.shape
    np.testing.assert_allclose(baked, source, atol=1e-3)


def test_strict_mode_does_not_bake(fresh_scene, export_ctx, world,
                                   log_capture):
    assert export_ctx.strict
    world.export_world(export_ctx, make_sky_world())
    assert list(export_ctx.scene_data.keys()) == ['type']
    assert any(level == 'WARN' for level, _ in log_capture)


def test_bake_can_be_turned_off(fresh_scene, bake_ctx, world, log_capture):
    bake_ctx.bake_world = False
    world.export_world(bake_ctx, make_sky_world())
    assert list(bake_ctx.scene_data.keys()) == ['type']
    assert any(level == 'WARN' for level, _ in log_capture)


def test_translatable_world_is_not_baked(fresh_scene, bake_ctx, world,
                                         tmp_path):
    world.export_world(bake_ctx, make_env_world(tmp_path, strength=1.5))
    params = only_emitter(bake_ctx)
    # The source image is exported as it is, and the strength is kept
    assert params['filename'] == 'textures/env.exr'
    assert params['scale'] == pytest.approx(1.5)


def test_baked_world_keeps_its_ray_visibility(fresh_scene, bake_ctx, world,
                                              tmp_path):
    b_world = make_sky_world()
    flags = getattr(b_world, 'cycles_visibility', None)
    if flags is None:
        pytest.skip('the Cycles ray visibility flags are unavailable')
    flags.camera = False
    world.export_world(bake_ctx, b_world)
    params = only_emitter(bake_ctx)
    assert params['visibility'] == world.world_visibility(b_world)
    # A world the camera does not see must still bake to what it emits
    assert read_rgb(os.path.join(str(tmp_path),
                                 params['filename'])).max() > 0.0


def make_light_path_world(lighting, backdrop, group=False):
    """A world showing the camera one backdrop and lighting the scene with
    another, selected by a Light Path node, optionally inside a group."""
    b_world = make_mix_shader_world(name='LightPathWorld',
                                    colors=(lighting, backdrop))
    tree = b_world.node_tree
    mix = next(node for node in tree.nodes if node.type == 'MIX_SHADER')
    if not group:
        light_path = tree.nodes.new('ShaderNodeLightPath')
        tree.links.new(light_path.outputs['Is Camera Ray'], mix.inputs['Fac'])
        return b_world, tree

    node_tree = bpy.data.node_groups.new('CameraRay', 'ShaderNodeTree')
    node_tree.interface.new_socket('Fac', in_out='OUTPUT',
                                   socket_type='NodeSocketFloat')
    light_path = node_tree.nodes.new('ShaderNodeLightPath')
    node_tree.links.new(light_path.outputs['Is Camera Ray'],
                        node_tree.nodes.new('NodeGroupOutput').inputs['Fac'])
    node = tree.nodes.new('ShaderNodeGroup')
    node.node_tree = node_tree
    tree.links.new(node.outputs['Fac'], mix.inputs['Fac'])
    return b_world, node_tree


@pytest.mark.parametrize('group', [False, True])
def test_light_path_world_bakes_its_lighting_branch(fresh_scene, bake_ctx,
                                                    world, tmp_path, group):
    lighting, backdrop = (0.0, 0.5, 0.0, 1.0), (0.5, 0.0, 0.0, 1.0)
    b_world, tree = make_light_path_world(lighting, backdrop, group)
    groups = len(bpy.data.node_groups)

    world.export_world(bake_ctx, b_world)
    params = only_emitter(bake_ctx)
    baked = read_rgb(os.path.join(str(tmp_path), params['filename']))
    np.testing.assert_allclose(baked.reshape(-1, 3).mean(axis=0),
                               lighting[:3], atol=1e-3)
    # The bake copies what it rewrites and cleans the copies up
    light_path = next(node for node in tree.nodes
                      if node.type == 'LIGHT_PATH')
    assert len(light_path.outputs['Is Camera Ray'].links) == 1
    assert len(bpy.data.node_groups) == groups
