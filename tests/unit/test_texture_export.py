"""Tests for the texture and vector-input export converters."""

import filecmp
import importlib
import math
import os
import sys
from contextlib import contextmanager

import bpy
import numpy as np
import pytest
from mathutils import Matrix

# The v -> 1 - v flip the mesh exporter applies to UV coordinates
FLIP = Matrix.Translation((0.0, 1.0, 0.0)) \
    @ Matrix.Diagonal((1.0, -1.0, 1.0, 1.0))

@contextmanager
def saved_file_resolver():
    '''Restore the state of Mitsuba's session-global file resolver on exit.'''
    fr = mi.file_resolver()
    paths = list(fr)
    try:
        yield fr
    finally:
        fr.clear()
        for path in paths:
            fr.append(path)

@contextmanager
def resolver_append(directory):
    '''Temporarily add a directory to Mitsuba's file resolver.'''
    with saved_file_resolver() as fr:
        fr.prepend(directory)
        yield



@pytest.fixture(scope='session')
def eval_mod(mi_addon):
    return importlib.import_module(
        f'{mi_addon}.convert.export.materials._resolve')


@pytest.fixture(scope='session')
def ref(eval_mod):
    return lambda node, stack=(): eval_mod.NodeRef(node, stack)


@pytest.fixture(scope='session')
def registry(mi_addon):
    return importlib.import_module(f'{mi_addon}.convert.export.materials')


@pytest.fixture(scope='session')
def textures(mi_addon):
    return importlib.import_module(
        f'{mi_addon}.convert.export.materials.textures')


@pytest.fixture
def exporter(mi_addon):
    import mitsuba as mi

    def _export(directory, render=False):
        mi.set_variant('scalar_rgb')
        bpy.context.scene.render.engine = 'MITSUBA'
        converter = sys.modules[mi_addon].io.exporter.SceneConverter(
            render=render)
        converter.export_ctx.directory = str(directory)
        converter.scene_to_dict(bpy.context.evaluated_depsgraph_get())
        return converter

    return _export


@pytest.fixture
def export_ctx(mi_addon, tmp_path):
    import mitsuba as mi
    mi.set_variant('scalar_rgb')
    ctx = sys.modules[mi_addon].io.exporter.export_context.ExportContext()
    ctx.directory = str(tmp_path)
    return ctx


def make_image(name='Tex', size=2, colorspace='sRGB'):
    image = bpy.data.images.new(name, size, size, alpha=True)
    # Changing the color space reloads generated images, so set it first
    image.colorspace_settings.name = colorspace
    values = np.linspace(0.0, 1.0, size * size * 4, dtype=np.float32)
    image.pixels.foreach_set(values)
    return image


def save_image(image, path):
    image.filepath_raw = str(path)
    image.file_format = 'PNG'
    image.save()
    return image


def make_diffuse_with_texture(node_type, name='Textured'):
    """A diffuse material with a texture node linked to its Color input."""
    b_mat = bpy.data.materials.new(name)
    b_mat.use_nodes = True
    tree = b_mat.node_tree
    tree.nodes.remove(tree.nodes['Principled BSDF'])
    diffuse = tree.nodes.new('ShaderNodeBsdfDiffuse')
    tree.links.new(diffuse.outputs['BSDF'],
                   tree.nodes['Material Output'].inputs['Surface'])
    tex = tree.nodes.new(node_type)
    tree.links.new(tex.outputs[0], diffuse.inputs['Color'])
    return b_mat, tex


def assign_material(b_mat, object_name='Cube'):
    b_obj = bpy.data.objects[object_name]
    b_obj.data.materials.clear()
    b_obj.data.materials.append(b_mat)


def reflectance_of(converter, mat_id):
    entry = converter.export_ctx.data_get(mat_id)
    return entry['bsdf']['reflectance']


###################
##  File export  ##
###################

def test_image_texture_file_export(fresh_scene, exporter, tmp_path):
    source_dir = tmp_path / 'source'
    source_dir.mkdir()
    image = save_image(make_image(), source_dir / 'tex.png')
    image_count = len(bpy.data.images)
    mtime = os.path.getmtime(source_dir / 'tex.png')

    b_mat, tex = make_diffuse_with_texture('ShaderNodeTexImage')
    tex.image = image
    assign_material(b_mat)

    export_dir = tmp_path / 'scene'
    export_dir.mkdir()
    converter = exporter(export_dir)
    params = reflectance_of(converter, 'mat-Textured')
    assert set(params) == {'type', 'filename', 'to_uv'}
    assert params['type'] == 'bitmap'
    assert params['filename'] == 'textures/tex.png'
    assert np.allclose(np.array(params['to_uv'].matrix), np.array(FLIP),
                       atol=1e-6)

    # The source file is copied verbatim and the datablock is untouched
    assert filecmp.cmp(source_dir / 'tex.png',
                       export_dir / 'textures' / 'tex.png', shallow=False)
    assert os.path.getmtime(source_dir / 'tex.png') == mtime
    assert image.filepath_raw == str(source_dir / 'tex.png')
    assert image.file_format == 'PNG'
    assert len(bpy.data.images) == image_count


def test_image_texture_raw_colorspace(fresh_scene, exporter, tmp_path):
    image = save_image(make_image(colorspace='Non-Color'), tmp_path / 'n.png')
    b_mat, tex = make_diffuse_with_texture('ShaderNodeTexImage')
    tex.image = image
    assign_material(b_mat)

    converter = exporter(tmp_path)
    params = reflectance_of(converter, 'mat-Textured')
    assert params['raw'] is True


def test_image_texture_sampling_modes(fresh_scene, exporter, tmp_path):
    image = save_image(make_image(), tmp_path / 'tex.png')
    b_mat, tex = make_diffuse_with_texture('ShaderNodeTexImage')
    tex.image = image
    tex.interpolation = 'Closest'
    tex.extension = 'MIRROR'
    assign_material(b_mat)

    converter = exporter(tmp_path)
    params = reflectance_of(converter, 'mat-Textured')
    assert params['filter_type'] == 'nearest'
    assert params['wrap_mode'] == 'mirror'

    tex.extension = 'EXTEND'
    converter = exporter(tmp_path)
    entries = [v for k, v in converter.export_ctx.scene_data.items()
               if k == 'mat-Textured']
    assert entries[0]['bsdf']['reflectance']['wrap_mode'] == 'clamp'


def test_unsaved_image_written_without_side_effects(fresh_scene, exporter,
                                                    tmp_path):
    image = make_image('Generated')
    image_count = len(bpy.data.images)
    b_mat, tex = make_diffuse_with_texture('ShaderNodeTexImage')
    tex.image = image
    assign_material(b_mat)

    converter = exporter(tmp_path)
    params = reflectance_of(converter, 'mat-Textured')
    assert params['filename'] == 'textures/Generated.png'
    # The datablock was not redirected to the exported file
    assert image.filepath_raw == ''
    assert len(bpy.data.images) == image_count

    # The written file holds the pixel buffer (byte-quantized)
    loaded = bpy.data.images.load(str(tmp_path / 'textures/Generated.png'))
    pixels = np.zeros(2 * 2 * 4, dtype=np.float32)
    loaded.pixels.foreach_get(pixels)
    original = np.zeros(2 * 2 * 4, dtype=np.float32)
    image.pixels.foreach_get(original)
    assert np.allclose(pixels, original, atol=1.0 / 255.0)


def test_image_export_dedup_and_name_clash(fresh_scene, export_ctx,
                                           textures, tmp_path):
    image = make_image('Shared')
    first , _ = textures.export_image(export_ctx, image)
    second, _ =  textures.export_image(export_ctx, image) 
    assert first == second

    assert os.listdir(tmp_path / 'textures') == ['Shared.png']

    # A different image saved under the same basename gets a fresh name
    other_dir = tmp_path / 'other'
    other_dir.mkdir()
    other = save_image(make_image('Other'), other_dir / 'Shared.png')
    third, _ = textures.export_image(export_ctx, other)
    assert third != first
    assert sorted(os.listdir(tmp_path / 'textures')) == \
        ['Shared-1.png', 'Shared.png']


#####################
##  Render export  ##
#####################

def test_image_texture_render_mode(fresh_scene, export_ctx, registry, tmp_path):
    import mitsuba as mi

    export_ctx.render = True
    image = make_image('InMemory', size=2)
    b_mat, tex = make_diffuse_with_texture('ShaderNodeTexImage')
    tex.image = image

    entry = registry.convert_material(export_ctx, b_mat)['bsdf']
    params = entry['bsdf']['reflectance']
    assert params['filename'].endswith('.png')
    assert (tmp_path / params['filename']).is_file()
    assert params.get('raw', False) is False



def test_render_mode_data_image_is_raw(fresh_scene, export_ctx, registry):
    export_ctx.render = True
    b_mat, tex = make_diffuse_with_texture('ShaderNodeTexImage')
    tex.image = make_image('Data', size=2, colorspace='Non-Color')

    entry = registry.convert_material(export_ctx, b_mat)['bsdf']
    params = entry['bsdf']['reflectance']
    assert params['raw'] is True
    assert params['filename'].endswith('.png')


def test_render_export_instantiates_textured_bsdf(fresh_scene, exporter,
                                                  tmp_path):
    image = make_image('InMemory', size=2)
    b_mat, tex = make_diffuse_with_texture('ShaderNodeTexImage')
    tex.image = image
    assign_material(b_mat)

    converter = exporter(tmp_path, render=True)
    assert 'mat-Textured' in converter.export_ctx.scene_data
    assert (tmp_path / 'textures').exists()
    scene = converter.dict_to_scene()
    assert len(scene.shapes()) > 0



######################
##  UV coordinates  ##
######################

def test_mapping_chain_to_uv(fresh_scene, exporter, tmp_path):
    image = save_image(make_image(), tmp_path / 'tex.png')
    b_mat, tex = make_diffuse_with_texture('ShaderNodeTexImage')
    tex.image = image
    tree = b_mat.node_tree
    mapping = tree.nodes.new('ShaderNodeMapping')
    mapping.vector_type = 'POINT'
    mapping.inputs['Location'].default_value = (0.1, 0.2, 0.0)
    mapping.inputs['Rotation'].default_value = (0.0, 0.0, math.pi / 2)
    mapping.inputs['Scale'].default_value = (2.0, 3.0, 1.0)
    coords = tree.nodes.new('ShaderNodeTexCoord')
    tree.links.new(coords.outputs['UV'], mapping.inputs['Vector'])
    tree.links.new(mapping.outputs['Vector'], tex.inputs['Vector'])
    assign_material(b_mat)

    converter = exporter(tmp_path)
    params = reflectance_of(converter, 'mat-Textured')

    from mathutils import Euler
    blender = Matrix.Translation((0.1, 0.2, 0.0)) \
        @ Euler((0.0, 0.0, math.pi / 2)).to_matrix().to_4x4() \
        @ Matrix.Diagonal((2.0, 3.0, 1.0, 1.0))
    assert np.allclose(np.array(params['to_uv'].matrix),
                       np.array(FLIP @ blender), atol=1e-6)


def test_mapping_texture_mode_is_inverse(fresh_scene, exporter, tmp_path):
    image = save_image(make_image(), tmp_path / 'tex.png')
    b_mat, tex = make_diffuse_with_texture('ShaderNodeTexImage')
    tex.image = image
    tree = b_mat.node_tree
    mapping = tree.nodes.new('ShaderNodeMapping')
    mapping.vector_type = 'TEXTURE'
    mapping.inputs['Scale'].default_value = (2.0, 4.0, 1.0)
    coords = tree.nodes.new('ShaderNodeTexCoord')
    tree.links.new(coords.outputs['UV'], mapping.inputs['Vector'])
    tree.links.new(mapping.outputs['Vector'], tex.inputs['Vector'])
    assign_material(b_mat)

    converter = exporter(tmp_path)
    params = reflectance_of(converter, 'mat-Textured')
    blender = Matrix.Diagonal((0.5, 0.25, 1.0, 1.0))
    assert np.allclose(np.array(params['to_uv'].matrix),
                       np.array(FLIP @ blender), atol=1e-6)


def test_unsupported_mapping_chain_is_ignored(fresh_scene, exporter,
                                              tmp_path):
    image = save_image(make_image(), tmp_path / 'tex.png')
    b_mat, tex = make_diffuse_with_texture('ShaderNodeTexImage')
    tex.image = image
    tree = b_mat.node_tree
    coords = tree.nodes.new('ShaderNodeTexCoord')
    tree.links.new(coords.outputs['Object'], tex.inputs['Vector'])
    assign_material(b_mat)

    converter = exporter(tmp_path)
    params = reflectance_of(converter, 'mat-Textured')
    # The mapping is dropped, but the row convention still has to survive
    assert np.allclose(np.array(params['to_uv'].matrix), np.array(FLIP),
                       atol=1e-6)


###############
##  Checker  ##
###############

def test_checker_export(fresh_scene, exporter, tmp_path):
    import mitsuba as mi

    b_mat, tex = make_diffuse_with_texture('ShaderNodeTexChecker')
    tex.inputs['Color1'].default_value = (1.0, 0.0, 0.0, 1.0)
    tex.inputs['Color2'].default_value = (0.0, 0.0, 1.0, 1.0)
    tex.inputs['Scale'].default_value = 4.0
    assign_material(b_mat)

    converter = exporter(tmp_path)
    params = reflectance_of(converter, 'mat-Textured')
    assert params['type'] == 'checkerboard'
    assert params['color0'] == {'type': 'rgb',
                                'value': pytest.approx([1.0, 0.0, 0.0])}
    assert params['color1'] == {'type': 'rgb',
                                'value': pytest.approx([0.0, 0.0, 1.0])}
    expected = [[2, 0, 0, 0], [0, 2, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    assert np.allclose(np.array(params['to_uv'].matrix), expected,
                       atol=1e-6)
    assert mi.load_dict(params) is not None


def test_checker_matches_blender_pattern(fresh_scene, exporter, tmp_path):
    import mitsuba as mi

    scale = 3.0
    b_mat, tex = make_diffuse_with_texture('ShaderNodeTexChecker')
    tex.inputs['Color1'].default_value = (1.0, 1.0, 1.0, 1.0)
    tex.inputs['Color2'].default_value = (0.0, 0.0, 0.0, 1.0)
    tex.inputs['Scale'].default_value = scale
    assign_material(b_mat)

    converter = exporter(tmp_path)
    texture = mi.load_dict(reflectance_of(converter, 'mat-Textured'))

    si = mi.SurfaceInteraction3f()
    for u in np.linspace(0.05, 0.95, 7):
        for v in np.linspace(0.05, 0.95, 7):
            # Blender shows Color1 where the cell parity is even
            expected = (math.floor(scale * u) + math.floor(scale * v)) \
                % 2 == 0
            si.uv = [u, v]  # texture coordinates port over verbatim
            value = texture.eval(si)[0]
            assert (value > 0.5) == expected, (u, v)


####################
##  Vertex color  ##
####################

def test_vertex_color_export(fresh_scene, exporter, tmp_path):
    b_mat, tex = make_diffuse_with_texture('ShaderNodeVertexColor')
    tex.layer_name = 'Col'
    assign_material(b_mat)

    converter = exporter(tmp_path)
    params = reflectance_of(converter, 'mat-Textured')
    assert params == {'type': 'mesh_attribute', 'name': 'vertex_Col'}


def test_alpha_output_is_unsupported(fresh_scene, export_ctx, registry):
    b_mat, tex = make_diffuse_with_texture('ShaderNodeTexImage')
    tex.image = make_image()
    diffuse = next(n for n in b_mat.node_tree.nodes
                   if n.type == 'BSDF_DIFFUSE')
    b_mat.node_tree.links.new(tex.outputs['Alpha'],
                              diffuse.inputs['Roughness'])

    result = registry.resolve(export_ctx, diffuse.inputs['Roughness'])
    assert isinstance(result, registry.Unsupported)


###########################
##  Normal and bump map  ##
###########################

def make_normal_chain(node_type):
    b_mat = bpy.data.materials.new('NormalChain')
    b_mat.use_nodes = True
    tree = b_mat.node_tree
    diffuse = tree.nodes.new('ShaderNodeBsdfDiffuse')
    wrapper = tree.nodes.new(node_type)
    tree.links.new(wrapper.outputs[0], diffuse.inputs['Normal'])
    tex = tree.nodes.new('ShaderNodeTexImage')
    tex.image = make_image('NormalTex', colorspace='Non-Color')
    return diffuse, wrapper, tex


def test_normalmap_wrap(fresh_scene, export_ctx, textures):
    export_ctx.render = True
    diffuse, normal_map, tex = make_normal_chain('ShaderNodeNormalMap')
    tree = diffuse.id_data
    tree.links.new(tex.outputs['Color'], normal_map.inputs['Color'])

    bsdf = {'type': 'diffuse'}
    result = textures.convert_normal_input(
        export_ctx, diffuse.inputs['Normal'], bsdf)
    assert result['type'] == 'normalmap'
    assert result['bsdf'] is bsdf
    assert result['normalmap']['type'] == 'bitmap'
    assert result['normalmap']['raw'] is True

    import mitsuba as mi
    with saved_file_resolver() as fr:
        fr.prepend(mi.filesystem.path(export_ctx.directory))
        assert mi.load_dict(result) is not None


def test_bumpmap_wrap(fresh_scene, export_ctx, textures):
    export_ctx.render = True
    diffuse, bump, tex = make_normal_chain('ShaderNodeBump')
    tree = diffuse.id_data
    tree.links.new(tex.outputs['Color'], bump.inputs['Height'])
    bump.inputs['Strength'].default_value = 0.5
    bump.inputs['Distance'].default_value = 0.3

    result = textures.convert_normal_input(
        export_ctx, diffuse.inputs['Normal'], {'type': 'diffuse'})
    assert result['type'] == 'bumpmap'
    assert result['scale'] == pytest.approx(0.15)
    assert result['texture']['type'] == 'bitmap'

    import mitsuba as mi
    with saved_file_resolver() as fr:
        fr.prepend(mi.filesystem.path(export_ctx.directory))
        assert mi.load_dict(result) is not None


def test_bump_over_normalmap(fresh_scene, export_ctx, textures):
    export_ctx.render = True
    diffuse, bump, tex = make_normal_chain('ShaderNodeBump')
    tree = diffuse.id_data
    tree.links.new(tex.outputs['Color'], bump.inputs['Height'])
    normal_map = tree.nodes.new('ShaderNodeNormalMap')
    normal_tex = tree.nodes.new('ShaderNodeTexImage')
    normal_tex.image = make_image('Inner', colorspace='Non-Color')
    tree.links.new(normal_tex.outputs['Color'], normal_map.inputs['Color'])
    tree.links.new(normal_map.outputs['Normal'], bump.inputs['Normal'])

    result = textures.convert_normal_input(
        export_ctx, diffuse.inputs['Normal'], {'type': 'diffuse'})
    assert result['type'] == 'bumpmap'
    assert result['bsdf']['type'] == 'normalmap'
    assert result['bsdf']['bsdf'] == {'type': 'diffuse'}


def test_unlinked_and_constant_normal_input(fresh_scene, export_ctx,
                                            textures):
    b_mat = bpy.data.materials.new('Plain')
    b_mat.use_nodes = True
    diffuse = b_mat.node_tree.nodes.new('ShaderNodeBsdfDiffuse')
    bsdf = {'type': 'diffuse'}
    assert textures.convert_normal_input(
        export_ctx, diffuse.inputs['Normal'], bsdf) is bsdf

    # A constant normal map color has no effect either
    diffuse2, normal_map, _ = make_normal_chain('ShaderNodeNormalMap')
    assert textures.convert_normal_input(
        export_ctx, diffuse2.inputs['Normal'], bsdf) is bsdf


def test_unsupported_normal_input(fresh_scene, export_ctx, textures):
    b_mat = bpy.data.materials.new('Weird')
    b_mat.use_nodes = True
    tree = b_mat.node_tree
    diffuse = tree.nodes.new('ShaderNodeBsdfDiffuse')
    geometry = tree.nodes.new('ShaderNodeNewGeometry')
    tree.links.new(geometry.outputs['Normal'], diffuse.inputs['Normal'])
    bsdf = {'type': 'diffuse'}
    assert textures.convert_normal_input(
        export_ctx, diffuse.inputs['Normal'], bsdf) is bsdf


###########################
##  Environment texture  ##
###########################

def make_environment_node(tmp_path=None):
    world = bpy.data.worlds.new('EnvWorld')
    world.use_nodes = True
    node = world.node_tree.nodes.new('ShaderNodeTexEnvironment')
    node.image = make_image('Env', size=4)
    if tmp_path is not None:
        save_image(node.image, tmp_path / 'env.png')
    return node


def test_environment_texture_file(fresh_scene, export_ctx, textures,
                                  tmp_path, ref):
    node = make_environment_node(tmp_path)
    params = textures.convert_environment_texture(export_ctx, ref(node))
    assert params == {'type': 'envmap', 'filename': 'textures/env.png'}
    assert (tmp_path / 'textures' / 'env.png').exists()


def test_environment_texture_render(fresh_scene, export_ctx, textures, ref):
    import mitsuba as mi
    export_ctx.render = True
    node = make_environment_node()
    params = textures.convert_environment_texture(export_ctx, ref(node))
    assert params['type'] == 'envmap'
    assert 'bitmap' not in params
    assert params['filename'].endswith(('.exr', '.hdr', '.png'))


def test_vertex_color_name_matches_mesh_attribute(fresh_scene, exporter,
                                                  tmp_path):
    # Attribute names with non-identifier characters are sanitized by the
    # mesh exporter; the mesh_attribute reference must match
    b_mesh = bpy.data.objects['Cube'].data
    attr = b_mesh.color_attributes.new('My Color', 'FLOAT_COLOR', 'POINT')
    color = np.tile([0.25, 0.5, 0.75, 1.0], len(b_mesh.vertices))
    attr.data.foreach_set('color', color)

    b_mat, tex = make_diffuse_with_texture('ShaderNodeVertexColor')
    tex.layer_name = 'My Color'
    assign_material(b_mat)

    converter = exporter(tmp_path)
    params = reflectance_of(converter, 'mat-Textured')
    assert params['name'] == 'vertex_My_Color'

    import mitsuba as mi
    scene = converter.dict_to_scene()
    mesh = next(s for s in scene.shapes() if isinstance(s, mi.Mesh))
    assert params['name'] in mi.traverse(mesh).keys()
