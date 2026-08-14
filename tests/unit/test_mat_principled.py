"""Unit tests for the Principled BSDF converters (export and import)."""

import importlib
import sys

import bpy
import pytest


@pytest.fixture(scope='session')
def registry(mi_addon):
    return importlib.import_module(f'{mi_addon}.convert.export.materials')


@pytest.fixture
def exporter(mi_addon):
    """Exports the current scene and returns the SceneConverter."""
    import mitsuba as mi

    def _export(directory, render=False):
        mi.set_variant('scalar_rgb')
        bpy.context.scene.render.engine = 'MITSUBA'
        converter = sys.modules[mi_addon].io.exporter.SceneConverter(render=render)
        converter.export_ctx.directory = str(directory)
        converter.scene_to_dict(bpy.context.evaluated_depsgraph_get())
        return converter

    return _export

@pytest.fixture
def fake_uniform_texture(registry):
    """Stand-in TEX_IMAGE converter returning a constant texture, so a
    texture's average is exactly known regardless of the sampling grid."""
    converters = registry._resolve._texture_converters
    previous = converters.get('TEX_IMAGE')

    @registry.texture_converter('TEX_IMAGE')
    def convert_fake_uniform(export_ctx, node, out_socket):
        return {'type': 'uniform', 'value': 0.25}

    yield {'type': 'uniform', 'value': 0.25}
    if previous is None:
        del converters['TEX_IMAGE']
    else:
        converters['TEX_IMAGE'] = previous

@pytest.fixture
def fake_image_texture(registry):
    """Registers a stand-in TEX_IMAGE texture converter, restoring any
    previously registered one afterwards."""
    converters = registry._resolve._texture_converters
    previous = converters.get('TEX_IMAGE')

    @registry.texture_converter('TEX_IMAGE')
    def convert_fake_image(export_ctx, node, out_socket):
        return {'type': 'checkerboard'}

    yield {'type': 'checkerboard'}
    if previous is None:
        del converters['TEX_IMAGE']
    else:
        converters['TEX_IMAGE'] = previous


def principled_node(name='Material'):
    return bpy.data.materials[name].node_tree.nodes['Principled BSDF']


def exported_entry(exporter, tmp_path, mat_id='mat-Material'):
    converter = exporter(tmp_path)
    return converter, converter.export_ctx.data_get(mat_id)


######################
##   Export  side   ##
######################

def test_export_default_material(fresh_scene, exporter, tmp_path):
    converter, entry = exported_entry(exporter, tmp_path)

    assert entry['type'] == 'twosided'
    params = entry['bsdf']
    assert params['type'] == 'principled'
    assert params['base_color']['value'] == pytest.approx([0.8, 0.8, 0.8])
    assert params['roughness'] == pytest.approx(0.5)
    assert params['metallic'] == 0.0
    assert params['anisotropic'] == 0.0
    assert params['spec_trans'] == 0.0
    assert params['specular'] == pytest.approx(0.5)
    assert params['spec_tint'] == pytest.approx(0.0)
    assert params['sheen'] == 0.0
    assert params['clearcoat'] == 0.0
    assert params['clearcoat_gloss'] == pytest.approx(0.97)
    assert 'eta' not in params

    # No emission by default: the material is not stored as a bsdf/emitter pair
    assert 'mat-Material' not in converter.export_ctx.exported_mats

    import mitsuba as mi
    assert mi.load_dict(entry) is not None


def test_export_reflective_values(fresh_scene, exporter, tmp_path):
    node = principled_node()
    node.inputs['Base Color'].default_value = (0.2, 0.4, 0.6, 1.0)
    node.inputs['Roughness'].default_value = 0.3
    node.inputs['Metallic'].default_value = 0.7
    node.inputs['Anisotropic'].default_value = 0.2
    node.inputs['Specular IOR Level'].default_value = 0.4
    node.inputs['Specular Tint'].default_value = (0.25, 0.25, 0.25, 1.0)
    node.inputs['Sheen Weight'].default_value = 0.6
    node.inputs['Sheen Tint'].default_value = (0.5, 0.5, 0.5, 1.0)
    node.inputs['Coat Weight'].default_value = 0.8
    node.inputs['Coat Roughness'].default_value = 0.1

    _, entry = exported_entry(exporter, tmp_path)
    params = entry['bsdf']
    assert params['base_color']['value'] == pytest.approx([0.2, 0.4, 0.6])
    # Blender and Mitsuba share the perceptual roughness convention
    assert params['roughness'] == pytest.approx(0.3)
    assert params['metallic'] == pytest.approx(0.7)
    assert params['anisotropic'] == pytest.approx(0.2)
    assert params['specular'] == pytest.approx(0.4)
    assert params['spec_tint'] == pytest.approx(0.75)
    assert params['sheen'] == pytest.approx(0.6)
    assert params['sheen_tint'] == pytest.approx(0.5)
    assert params['clearcoat'] == pytest.approx(0.8)
    assert params['clearcoat_gloss'] == pytest.approx(0.9)


def test_export_transmissive_uses_eta(fresh_scene, exporter, tmp_path):
    node = principled_node()
    node.inputs['Transmission Weight'].default_value = 1.0
    node.inputs['IOR'].default_value = 1.45

    _, entry = exported_entry(exporter, tmp_path)
    # Transmissive materials are one-sided
    assert entry['type'] == 'principled'
    assert entry['spec_trans'] == pytest.approx(1.0)
    assert entry['eta'] == pytest.approx(1.45)
    assert 'specular' not in entry

    import mitsuba as mi
    assert mi.load_dict(entry) is not None


def test_export_emission(fresh_scene, exporter, tmp_path):
    node = principled_node()
    node.inputs['Emission Strength'].default_value = 2.0
    node.inputs['Emission Color'].default_value = (1.0, 0.5, 0.25, 1.0)

    converter, entry = exported_entry(exporter, tmp_path)
    assert entry['type'] == 'twosided'
    pair = converter.export_ctx.exported_mats['mat-Material']
    assert pair['bsdf'] == 'mat-Material'
    assert pair['emitter']['type'] == 'area'
    assert pair['emitter']['radiance']['value'] == \
        pytest.approx([2.0, 1.0, 0.5])


def test_export_black_emission_ignored(fresh_scene, exporter, tmp_path):
    node = principled_node()
    node.inputs['Emission Strength'].default_value = 5.0
    node.inputs['Emission Color'].default_value = (0.0, 0.0, 0.0, 1.0)

    converter, _ = exported_entry(exporter, tmp_path)
    assert 'mat-Material' not in converter.export_ctx.exported_mats


def test_export_alpha_wraps_mask(fresh_scene, exporter, tmp_path):
    principled_node().inputs['Alpha'].default_value = 0.25

    _, entry = exported_entry(exporter, tmp_path)
    assert entry['type'] == 'mask'
    assert entry['opacity'] == pytest.approx(0.25)
    assert entry['bsdf']['type'] == 'twosided'
    assert entry['bsdf']['bsdf']['type'] == 'principled'

    import mitsuba as mi
    assert mi.load_dict(entry) is not None


def test_export_textured_inputs(fresh_scene, exporter, tmp_path,
                                fake_image_texture):
    node = principled_node()
    tree = node.id_data
    tex = tree.nodes.new('ShaderNodeTexImage')
    tree.links.new(tex.outputs['Color'], node.inputs['Base Color'])
    tree.links.new(tex.outputs['Alpha'], node.inputs['Alpha'])

    _, entry = exported_entry(exporter, tmp_path)
    assert entry['type'] == 'mask'
    assert entry['opacity'] == fake_image_texture
    assert entry['bsdf']['bsdf']['base_color'] == fake_image_texture


def test_export_normal_map(fresh_scene, exporter, tmp_path,
                           fake_image_texture):
    node = principled_node()
    tree = node.id_data
    tex = tree.nodes.new('ShaderNodeTexImage')
    normal_map = tree.nodes.new('ShaderNodeNormalMap')
    tree.links.new(tex.outputs['Color'], normal_map.inputs['Color'])
    tree.links.new(normal_map.outputs['Normal'], node.inputs['Normal'])
    node.inputs['Alpha'].default_value = 0.5

    _, entry = exported_entry(exporter, tmp_path)
    # The mask wraps the normalmap, which wraps the two-sided BSDF
    assert entry['type'] == 'mask'
    assert entry['bsdf']['type'] == 'normalmap'
    assert entry['bsdf']['normalmap'] == fake_image_texture
    assert entry['bsdf']['bsdf']['type'] == 'twosided'
    assert entry['bsdf']['bsdf']['bsdf']['type'] == 'principled'

    import mitsuba as mi
    assert mi.load_dict(entry) is not None


def test_export_constant_bump_ignored(fresh_scene, exporter, tmp_path):
    # A Bump node with a constant height perturbs nothing
    node = principled_node()
    tree = node.id_data
    bump = tree.nodes.new('ShaderNodeBump')
    tree.links.new(bump.outputs['Normal'], node.inputs['Normal'])

    _, entry = exported_entry(exporter, tmp_path)
    assert entry['type'] == 'twosided'


def test_textured_coat_roughness_is_averaged(fresh_scene, exporter, tmp_path, fake_uniform_texture):
    node = principled_node()
    tree = node.id_data
    tex = tree.nodes.new('ShaderNodeTexImage')
    tree.links.new(tex.outputs['Color'], node.inputs['Coat Roughness'])

    _, entry = exported_entry(exporter, tmp_path)
    assert entry['bsdf']['clearcoat_gloss'] == pytest.approx(0.75)

def test_export_input_graph(fresh_scene, exporter, tmp_path):
    import mitsuba as mi, drjit as dr
    node = principled_node()
    tree = node.id_data
    math_node = tree.nodes.new('ShaderNodeMath')
    math_node.operation = 'MULTIPLY'
    math_node.inputs[0].default_value = 0.25
    math_node.inputs[1].default_value = 2.0
    tree.links.new(math_node.outputs['Value'], node.inputs['Metallic'])
    _, entry = exported_entry(exporter, tmp_path)

    tex = mi.load_dict(entry['bsdf']['metallic'])
    assert tex.eval_1(dr.zeros(mi.SurfaceInteraction3f)) == pytest.approx(0.5)


######################
##   Import  side   ##
######################

def import_xml(tmp_path, xml_body):
    xml = f'<scene version="3.0.0">\n{xml_body}\n</scene>'
    scene_file = tmp_path / 'scene.xml'
    scene_file.write_text(xml)
    assert bpy.ops.import_scene.mitsuba(filepath=str(scene_file)) == \
        {'FINISHED'}


def imported_material(name):
    b_mat = bpy.data.materials[name]
    surface = b_mat.node_tree.get_output_node('CYCLES').inputs['Surface']
    assert surface.is_linked
    return b_mat, surface.links[0].from_node


def test_import_principled(mi_addon, fresh_scene, tmp_path):
    import_xml(tmp_path, '''
        <shape type="sphere">
            <bsdf type="principled" id="mat-p">
                <rgb name="base_color" value="0.2 0.4 0.6"/>
                <float name="roughness" value="0.3"/>
                <float name="metallic" value="0.7"/>
                <float name="anisotropic" value="0.2"/>
                <float name="spec_trans" value="1.0"/>
                <float name="eta" value="1.45"/>
                <float name="spec_tint" value="0.25"/>
                <float name="sheen" value="0.6"/>
                <float name="sheen_tint" value="0.4"/>
                <float name="clearcoat" value="0.8"/>
                <float name="clearcoat_gloss" value="0.9"/>
            </bsdf>
        </shape>''')

    _, node = imported_material('mat-p')
    assert node.bl_idname == 'ShaderNodeBsdfPrincipled'
    inputs = node.inputs
    assert tuple(inputs['Base Color'].default_value) == \
        pytest.approx((0.2, 0.4, 0.6, 1.0))
    assert inputs['Roughness'].default_value == pytest.approx(0.3)
    assert inputs['Metallic'].default_value == pytest.approx(0.7)
    assert inputs['Anisotropic'].default_value == pytest.approx(0.2)
    assert inputs['Transmission Weight'].default_value == pytest.approx(1.0)
    assert inputs['IOR'].default_value == pytest.approx(1.45)
    assert inputs['Specular IOR Level'].default_value == \
        pytest.approx(((1.45 - 1.0) / (1.45 + 1.0)) ** 2 / 0.08)
    assert tuple(inputs['Specular Tint'].default_value) == \
        pytest.approx((0.75, 0.75, 0.75, 1.0))
    assert inputs['Sheen Weight'].default_value == pytest.approx(0.6)
    assert tuple(inputs['Sheen Tint'].default_value) == \
        pytest.approx((0.4, 0.4, 0.4, 1.0))
    assert inputs['Coat Weight'].default_value == pytest.approx(0.8)
    assert inputs['Coat Roughness'].default_value == pytest.approx(0.1)


def test_import_principled_specular(mi_addon, fresh_scene, tmp_path):
    import_xml(tmp_path, '''
        <shape type="sphere">
            <bsdf type="principled" id="mat-s">
                <float name="specular" value="0.5"/>
            </bsdf>
        </shape>''')

    _, node = imported_material('mat-s')
    assert node.inputs['Specular IOR Level'].default_value == \
        pytest.approx(0.5)
    # F0 = 0.08 * 0.5 = 0.04 corresponds to an IOR of 1.5
    assert node.inputs['IOR'].default_value == pytest.approx(1.5)


def test_import_principled_defaults(mi_addon, fresh_scene, tmp_path):
    import_xml(tmp_path, '''
        <shape type="sphere">
            <bsdf type="principled" id="mat-d"/>
        </shape>''')

    _, node = imported_material('mat-d')
    assert node.bl_idname == 'ShaderNodeBsdfPrincipled'
    assert tuple(node.inputs['Base Color'].default_value) == \
        pytest.approx((0.5, 0.5, 0.5, 1.0))
    assert node.inputs['Roughness'].default_value == pytest.approx(0.5)


def test_import_principled_with_emitter(mi_addon, fresh_scene, tmp_path):
    import_xml(tmp_path, '''
        <shape type="rectangle">
            <bsdf type="principled" id="mat-glow"/>
            <emitter type="area">
                <rgb name="radiance" value="2 1 0.5"/>
            </emitter>
        </shape>''')

    b_mat, node = imported_material('mat-glow')
    assert node.bl_idname == 'ShaderNodeAddShader'
    emission = [n for n in b_mat.node_tree.nodes
                if n.bl_idname == 'ShaderNodeEmission']
    assert len(emission) == 1
    assert emission[0].inputs['Strength'].default_value == pytest.approx(2.0)
    assert tuple(emission[0].inputs['Color'].default_value) == \
        pytest.approx((1.0, 0.5, 0.25, 1.0))
    principled = [n for n in b_mat.node_tree.nodes
                  if n.bl_idname == 'ShaderNodeBsdfPrincipled']
    assert len(principled) == 1
