"""Round-trip tests: textured materials through XML export and import."""

import importlib
import math
import sys

import bpy
import numpy as np
import pytest


@pytest.fixture(autouse=True)
def restore_texture_converters(mi_addon):
    """Other test modules temporarily replace registry entries (and drop
    them on cleanup); make sure the real converters are in place here."""
    textures = importlib.import_module(
        f'{mi_addon}.convert.export.materials.textures')
    eval_mod = importlib.import_module(
        f'{mi_addon}.convert.export.materials._eval')
    eval_mod._texture_converters.update({
        'TEX_IMAGE': textures.convert_image_texture,
        'TEX_CHECKER': textures.convert_checker_texture,
        'VERTEX_COLOR': textures.convert_vertex_color,
    })


@pytest.fixture
def exporter(mi_addon):
    import mitsuba as mi

    def _export(directory):
        mi.set_variant('scalar_rgb')
        bpy.context.scene.render.engine = 'MITSUBA'
        converter = sys.modules[mi_addon].io.exporter.SceneConverter()
        converter.export_ctx.directory = str(directory)
        converter.scene_to_dict(bpy.context.evaluated_depsgraph_get())
        return converter

    return _export


def make_diffuse_with_texture(node_type, name='Textured'):
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


def roundtrip(exporter, tmp_path, mat_id='mat-Textured'):
    converter = exporter(tmp_path)
    # The exporter wraps diffuse BSDFs in twosided, whose importer belongs
    # to the combinator converters; strip it so these tests only exercise
    # the texture converters
    entry = converter.export_ctx.data_get(mat_id)
    if entry.get('type') == 'twosided':
        converter.export_ctx.scene_data[mat_id] = entry['bsdf']
    converter.dict_to_xml(str(tmp_path / 'scene.xml'))
    bpy.ops.wm.read_homefile()
    assert bpy.ops.import_scene.mitsuba(
        filepath=str(tmp_path / 'scene.xml')) == {'FINISHED'}


def find_node(b_mat, bl_idname):
    nodes = [n for n in b_mat.node_tree.nodes if n.bl_idname == bl_idname]
    assert len(nodes) == 1
    return nodes[0]


def test_image_texture_roundtrip(mi_addon, fresh_scene, exporter, tmp_path):
    image = bpy.data.images.new('RoundTex', 4, 4, alpha=True)
    # Changing the color space reloads generated images, so set it first
    image.colorspace_settings.name = 'Non-Color'
    values = np.linspace(0.0, 1.0, 4 * 4 * 4, dtype=np.float32)
    image.pixels.foreach_set(values)

    b_mat, tex = make_diffuse_with_texture('ShaderNodeTexImage')
    tex.image = image
    tex.interpolation = 'Closest'
    tex.extension = 'EXTEND'
    assign_material(b_mat)

    roundtrip(exporter, tmp_path)

    b_mat = bpy.data.materials['mat-Textured']
    tex = find_node(b_mat, 'ShaderNodeTexImage')
    assert tex.interpolation == 'Closest'
    assert tex.extension == 'EXTEND'
    assert tex.image.colorspace_settings.name == 'Non-Color'
    assert tuple(tex.image.size) == (4, 4)

    loaded = np.zeros(4 * 4 * 4, dtype=np.float32)
    tex.image.pixels.foreach_get(loaded)
    # The PNG round trip quantizes the channels to 8 bits
    assert np.allclose(loaded, values, atol=1.0 / 255.0)


def test_mapping_roundtrip(mi_addon, fresh_scene, exporter, tmp_path):
    image = bpy.data.images.new('MapTex', 4, 4, alpha=True)
    image.colorspace_settings.name = 'Non-Color'

    b_mat, tex = make_diffuse_with_texture('ShaderNodeTexImage')
    tex.image = image
    tree = b_mat.node_tree
    mapping = tree.nodes.new('ShaderNodeMapping')
    mapping.inputs['Location'].default_value = (0.25, -0.5, 0.0)
    mapping.inputs['Rotation'].default_value = (0.0, 0.0, math.pi / 6)
    mapping.inputs['Scale'].default_value = (2.0, 0.5, 1.0)
    coords = tree.nodes.new('ShaderNodeTexCoord')
    tree.links.new(coords.outputs['UV'], mapping.inputs['Vector'])
    tree.links.new(mapping.outputs['Vector'], tex.inputs['Vector'])
    assign_material(b_mat)

    roundtrip(exporter, tmp_path)

    b_mat = bpy.data.materials['mat-Textured']
    mapping = find_node(b_mat, 'ShaderNodeMapping')
    assert tuple(mapping.inputs['Location'].default_value) == \
        pytest.approx((0.25, -0.5, 0.0), abs=1e-5)
    assert mapping.inputs['Rotation'].default_value[2] == \
        pytest.approx(math.pi / 6, abs=1e-5)
    assert tuple(mapping.inputs['Scale'].default_value) == \
        pytest.approx((2.0, 0.5, 1.0), abs=1e-5)
    tex = find_node(b_mat, 'ShaderNodeTexImage')
    assert tex.inputs['Vector'].links[0].from_node == mapping


def test_checker_roundtrip(mi_addon, fresh_scene, exporter, tmp_path):
    b_mat, tex = make_diffuse_with_texture('ShaderNodeTexChecker')
    tex.inputs['Color1'].default_value = (1.0, 0.0, 0.0, 1.0)
    tex.inputs['Color2'].default_value = (0.0, 0.0, 1.0, 1.0)
    tex.inputs['Scale'].default_value = 5.0
    assign_material(b_mat)

    roundtrip(exporter, tmp_path)

    b_mat = bpy.data.materials['mat-Textured']
    checker = find_node(b_mat, 'ShaderNodeTexChecker')
    assert tuple(checker.inputs['Color1'].default_value) == \
        pytest.approx((1.0, 0.0, 0.0, 1.0))
    assert tuple(checker.inputs['Color2'].default_value) == \
        pytest.approx((0.0, 0.0, 1.0, 1.0))
    assert checker.inputs['Scale'].default_value == pytest.approx(5.0)
    assert not checker.inputs['Vector'].is_linked


def test_vertex_color_roundtrip(mi_addon, fresh_scene, exporter, tmp_path):
    mesh = bpy.data.objects['Cube'].data
    mesh.color_attributes.new('Col', 'FLOAT_COLOR', 'CORNER')
    b_mat, tex = make_diffuse_with_texture('ShaderNodeVertexColor')
    tex.layer_name = 'Col'
    assign_material(b_mat)

    roundtrip(exporter, tmp_path)

    b_mat = bpy.data.materials['mat-Textured']
    color = find_node(b_mat, 'ShaderNodeVertexColor')
    assert color.layer_name == 'Col'


def test_normal_and_bump_roundtrip(mi_addon, fresh_scene, tmp_path):
    import mitsuba as mi
    mi.set_variant('scalar_rgb')

    textures = importlib.import_module(
        f'{mi_addon}.convert.export.materials.textures')
    export_context = sys.modules[mi_addon].io.exporter.export_context
    ctx = export_context.ExportContext()
    ctx.directory = str(tmp_path)

    b_mat = bpy.data.materials.new('Chain')
    b_mat.use_nodes = True
    tree = b_mat.node_tree
    diffuse = tree.nodes.new('ShaderNodeBsdfDiffuse')
    bump = tree.nodes.new('ShaderNodeBump')
    bump.inputs['Distance'].default_value = 0.4
    tree.links.new(bump.outputs['Normal'], diffuse.inputs['Normal'])
    height = tree.nodes.new('ShaderNodeTexImage')
    height.image = bpy.data.images.new('Height', 4, 4)
    height.image.colorspace_settings.name = 'Non-Color'
    tree.links.new(height.outputs['Color'], bump.inputs['Height'])
    normal_map = tree.nodes.new('ShaderNodeNormalMap')
    normal_tex = tree.nodes.new('ShaderNodeTexImage')
    normal_tex.image = bpy.data.images.new('Normal', 4, 4)
    normal_tex.image.colorspace_settings.name = 'Non-Color'
    tree.links.new(normal_tex.outputs['Color'], normal_map.inputs['Color'])
    tree.links.new(normal_map.outputs['Normal'], bump.inputs['Normal'])

    wrapped = textures.convert_normal_input(
        ctx, diffuse.inputs['Normal'], {'type': 'diffuse'})
    assert wrapped['type'] == 'bumpmap'
    assert wrapped['bsdf']['type'] == 'normalmap'

    scene_dict = {
        'type': 'scene',
        'shape': {'type': 'sphere', 'surface': wrapped},
    }
    config = mi.parser.ParserConfig(mi.variant())
    state = mi.parser.parse_dict(config, scene_dict)
    mi.parser.write_file(state, str(tmp_path / 'scene.xml'), True)

    bpy.ops.wm.read_homefile()
    assert bpy.ops.import_scene.mitsuba(
        filepath=str(tmp_path / 'scene.xml')) == {'FINISHED'}

    b_mat = next(m for m in bpy.data.materials
                 if m.node_tree and any(n.bl_idname == 'ShaderNodeBump'
                                        for n in m.node_tree.nodes))
    diffuse = find_node(b_mat, 'ShaderNodeBsdfDiffuse')
    bump = find_node(b_mat, 'ShaderNodeBump')
    normal_map = find_node(b_mat, 'ShaderNodeNormalMap')
    assert diffuse.inputs['Normal'].links[0].from_node == bump
    assert bump.inputs['Normal'].links[0].from_node == normal_map
    assert bump.inputs['Distance'].default_value == pytest.approx(0.4)
