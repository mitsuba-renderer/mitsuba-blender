"""Tests for the basic BSDF converters: Glossy, Glass, Refraction,
Transparent and Translucent on export; conductors, dielectrics and
plastics on import."""

import importlib
import math
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
        converter = sys.modules[mi_addon].io.exporter.SceneConverter(
            render=render)
        converter.export_ctx.directory = str(directory)
        converter.scene_to_dict(bpy.context.evaluated_depsgraph_get())
        return converter

    return _export


def make_material(node_idname, name='Basic'):
    """Creates a material whose surface is a single BSDF node and assigns
    it to the default cube."""
    b_mat = bpy.data.materials.new(name)
    b_mat.use_nodes = True
    tree = b_mat.node_tree
    tree.nodes.remove(tree.nodes['Principled BSDF'])
    node = tree.nodes.new(node_idname)
    tree.links.new(node.outputs[0],
                   tree.nodes['Material Output'].inputs['Surface'])
    b_obj = bpy.data.objects['Cube']
    b_obj.data.materials.clear()
    b_obj.data.materials.append(b_mat)
    return node


def export_entry(exporter, tmp_path, name='Basic'):
    converter = exporter(tmp_path)
    entry = converter.export_ctx.data_get(f'mat-{name}')
    assert entry is not None

    import mitsuba as mi
    assert mi.load_dict(entry) is not None
    return entry


def rgb(value):
    return {'type': 'rgb', 'value': pytest.approx(list(value))}


####################
##  Glossy BSDF   ##
####################

def test_export_glossy_smooth(fresh_scene, exporter, tmp_path):
    node = make_material('ShaderNodeBsdfAnisotropic')
    node.inputs['Color'].default_value = (0.8, 0.1, 0.1, 1.0)
    node.inputs['Roughness'].default_value = 0.0

    entry = export_entry(exporter, tmp_path)
    assert entry == {
        'type': 'twosided',
        'bsdf': {
            'type': 'conductor',
            'specular_reflectance': rgb([0.8, 0.1, 0.1]),
        },
    }


@pytest.mark.parametrize('bl_dist,mi_dist', [
    ('GGX', 'ggx'), ('BECKMANN', 'beckmann'),
    ('MULTI_GGX', 'ggx'), ('ASHIKHMIN_SHIRLEY', 'beckmann')])
def test_export_glossy_rough(fresh_scene, exporter, tmp_path, bl_dist,
                             mi_dist):
    node = make_material('ShaderNodeBsdfAnisotropic')
    node.distribution = bl_dist
    node.inputs['Roughness'].default_value = 0.5

    entry = export_entry(exporter, tmp_path)
    bsdf = entry['bsdf']
    assert bsdf['type'] == 'roughconductor'
    assert bsdf['distribution'] == mi_dist
    assert bsdf['alpha'] == pytest.approx(0.25)


@pytest.mark.parametrize('anisotropy', [0.5, -0.5])
def test_export_glossy_anisotropic(fresh_scene, exporter, tmp_path,
                                   anisotropy):
    node = make_material('ShaderNodeBsdfAnisotropic')
    node.distribution = 'GGX'
    node.inputs['Roughness'].default_value = 0.5
    node.inputs['Anisotropy'].default_value = anisotropy

    entry = export_entry(exporter, tmp_path)
    bsdf = entry['bsdf']
    aspect = math.sqrt(1.0 - 0.9 * abs(anisotropy))
    alpha_u, alpha_v = 0.25 / aspect, 0.25 * aspect
    if anisotropy < 0.0:
        alpha_u, alpha_v = alpha_v, alpha_u
    assert bsdf['alpha_u'] == pytest.approx(alpha_u)
    assert bsdf['alpha_v'] == pytest.approx(alpha_v)


def test_export_glossy_textured_roughness(fresh_scene, exporter, tmp_path,
                                          registry):
    @registry.texture_converter('TEX_BRICK')
    def convert_brick(export_ctx, node, out_socket):
        return {'type': 'checkerboard'}

    try:
        node = make_material('ShaderNodeBsdfAnisotropic')
        node.distribution = 'GGX'
        tree = node.id_data
        brick = tree.nodes.new('ShaderNodeTexBrick')
        tree.links.new(brick.outputs['Fac'], node.inputs['Roughness'])

        entry = export_entry(exporter, tmp_path)
        # Texture-driven roughness passes through without squaring
        assert entry['bsdf']['alpha'] == {'type': 'math',
                                          'op': 'POWER',
                                          'use_clamp': False,
                                          'a': {'type': 'checkerboard'},
                                          'b': 2.0,}
    finally:
        del registry._resolve._texture_converters['TEX_BRICK']


##########################
##  Glass & Refraction  ##
##########################

def test_export_glass_smooth(fresh_scene, exporter, tmp_path):
    node = make_material('ShaderNodeBsdfGlass')
    node.inputs['Color'].default_value = (0.7, 0.8, 0.9, 1.0)
    node.inputs['Roughness'].default_value = 0.0
    node.inputs['IOR'].default_value = 1.45

    entry = export_entry(exporter, tmp_path)
    assert entry == {
        'type': 'dielectric',
        'int_ior': pytest.approx(1.45),
        'specular_transmittance': rgb([0.7, 0.8, 0.9]),
    }


def test_export_glass_thin(fresh_scene, exporter, tmp_path):
    node = make_material('ShaderNodeBsdfGlass')
    node.inputs['Roughness'].default_value = 0.0
    node.inputs['IOR'].default_value = 1.0

    entry = export_entry(exporter, tmp_path)
    assert entry['type'] == 'thindielectric'


def test_export_glass_rough(fresh_scene, exporter, tmp_path):
    node = make_material('ShaderNodeBsdfGlass')
    node.distribution = 'GGX'
    node.inputs['Roughness'].default_value = 0.4
    node.inputs['IOR'].default_value = 1.45

    entry = export_entry(exporter, tmp_path)
    assert entry['type'] == 'roughdielectric'
    assert entry['distribution'] == 'ggx'
    assert entry['alpha'] == pytest.approx(0.16)
    assert entry['int_ior'] == pytest.approx(1.45)


def test_export_glass_unsupported_ior_input(fresh_scene, exporter, tmp_path):
    node = make_material('ShaderNodeBsdfGlass')
    node.inputs['Roughness'].default_value = 0.0
    node.inputs['IOR'].default_value = 1.6
    tree = node.id_data
    noise = tree.nodes.new('ShaderNodeTexNoise')
    tree.links.new(noise.outputs['Fac'], node.inputs['IOR'])

    # The unsupported IOR input falls back to the socket default
    entry = export_entry(exporter, tmp_path)
    assert entry['type'] == 'dielectric'
    assert entry['int_ior'] == pytest.approx(1.6)


def test_export_refraction(fresh_scene, exporter, tmp_path):
    node = make_material('ShaderNodeBsdfRefraction')
    node.distribution = 'BECKMANN'
    node.inputs['Color'].default_value = (0.9, 0.9, 0.9, 1.0)
    node.inputs['Roughness'].default_value = 0.3
    node.inputs['IOR'].default_value = 1.33

    entry = export_entry(exporter, tmp_path)
    assert entry['type'] == 'roughdielectric'
    assert entry['distribution'] == 'beckmann'
    assert entry['alpha'] == pytest.approx(0.09)
    assert entry['int_ior'] == pytest.approx(1.33)


def test_export_refraction_smooth(fresh_scene, exporter, tmp_path):
    node = make_material('ShaderNodeBsdfRefraction')
    node.inputs['Roughness'].default_value = 0.0
    node.inputs['IOR'].default_value = 1.33

    entry = export_entry(exporter, tmp_path)
    assert entry['type'] == 'dielectric'


##################################
##  Transparent & Translucent   ##
##################################

def test_export_transparent_white(fresh_scene, exporter, tmp_path):
    node = make_material('ShaderNodeBsdfTransparent')
    node.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)

    assert export_entry(exporter, tmp_path) == {'type': 'null'}


def test_export_transparent_tinted(fresh_scene, exporter, tmp_path):
    node = make_material('ShaderNodeBsdfTransparent')
    node.inputs['Color'].default_value = (0.25, 0.5, 0.75, 1.0)

    entry = export_entry(exporter, tmp_path)
    assert entry['type'] == 'mask'
    assert entry['opacity'] == rgb([0.75, 0.5, 0.25])
    assert entry['bsdf']['type'] == 'diffuse'
    assert entry['bsdf']['reflectance']['value'] == 0.0


def test_export_translucent(fresh_scene, exporter, tmp_path):
    node = make_material('ShaderNodeBsdfTranslucent')
    node.inputs['Color'].default_value = (0.2, 0.6, 0.4, 1.0)

    entry = export_entry(exporter, tmp_path)
    assert entry == {
        'type': 'principledthin',
        'base_color': rgb([0.2, 0.6, 0.4]),
        'diff_trans': 2.0,
    }


####################
##  Normal input  ##
####################

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


def link_normal_map(node):
    tree = node.id_data
    tex = tree.nodes.new('ShaderNodeTexImage')
    normal_map = tree.nodes.new('ShaderNodeNormalMap')
    tree.links.new(tex.outputs['Color'], normal_map.inputs['Color'])
    tree.links.new(normal_map.outputs['Normal'], node.inputs['Normal'])


def test_export_glossy_normal_map(fresh_scene, exporter, tmp_path,
                                  fake_image_texture):
    node = make_material('ShaderNodeBsdfAnisotropic')
    link_normal_map(node)

    entry = export_entry(exporter, tmp_path)
    assert entry['type'] == 'normalmap'
    assert entry['normalmap'] == fake_image_texture
    assert entry['bsdf']['type'] == 'twosided'


def test_export_glass_normal_map(fresh_scene, exporter, tmp_path,
                                 fake_image_texture):
    node = make_material('ShaderNodeBsdfGlass')
    link_normal_map(node)

    entry = export_entry(exporter, tmp_path)
    assert entry['type'] == 'normalmap'
    assert entry['normalmap'] == fake_image_texture
    assert entry['bsdf']['type'] == 'dielectric'


###################
##  Import side  ##
###################

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


def test_import_conductor(mi_addon, fresh_scene, tmp_path):
    import_xml(tmp_path, '''
        <shape type="sphere">
            <bsdf type="conductor" id="mat-gold">
                <string name="material" value="Au"/>
            </bsdf>
        </shape>''')

    _, node = imported_material('mat-gold')
    assert node.bl_idname == 'ShaderNodeBsdfAnisotropic'
    assert node.inputs['Roughness'].default_value == 0.0
    color = tuple(node.inputs['Color'].default_value)
    # Gold: strong red, weak blue
    assert color[0] > 0.8 and color[0] > color[1] > color[2]


def test_import_roughconductor(mi_addon, fresh_scene, tmp_path):
    import_xml(tmp_path, '''
        <shape type="sphere">
            <bsdf type="roughconductor" id="mat-brushed">
                <string name="distribution" value="ggx"/>
                <float name="alpha" value="0.09"/>
            </bsdf>
        </shape>''')

    _, node = imported_material('mat-brushed')
    assert node.bl_idname == 'ShaderNodeBsdfAnisotropic'
    assert node.distribution == 'GGX'
    assert node.inputs['Roughness'].default_value == pytest.approx(0.3)


def test_import_roughconductor_anisotropic(mi_addon, fresh_scene, tmp_path):
    # alpha_u/alpha_v as produced by the exporter for roughness 0.5,
    # anisotropy 0.5
    aspect = math.sqrt(1.0 - 0.9 * 0.5)
    import_xml(tmp_path, f'''
        <shape type="sphere">
            <bsdf type="roughconductor" id="mat-aniso">
                <float name="alpha_u" value="{0.25 / aspect}"/>
                <float name="alpha_v" value="{0.25 * aspect}"/>
            </bsdf>
        </shape>''')

    _, node = imported_material('mat-aniso')
    assert node.inputs['Roughness'].default_value == pytest.approx(0.5)
    assert node.inputs['Anisotropy'].default_value == \
        pytest.approx(0.5, rel=1e-4)


def test_import_dielectric(mi_addon, fresh_scene, tmp_path):
    import_xml(tmp_path, '''
        <shape type="sphere">
            <bsdf type="dielectric" id="mat-glass">
                <float name="int_ior" value="1.45"/>
                <rgb name="specular_transmittance" value="0.7 0.8 0.9"/>
            </bsdf>
        </shape>''')

    _, node = imported_material('mat-glass')
    assert node.bl_idname == 'ShaderNodeBsdfGlass'
    assert node.inputs['Roughness'].default_value == 0.0
    assert node.inputs['IOR'].default_value == pytest.approx(1.45)
    assert tuple(node.inputs['Color'].default_value) == \
        pytest.approx((0.7, 0.8, 0.9, 1.0))


def test_import_dielectric_named_ior(mi_addon, fresh_scene, tmp_path):
    import_xml(tmp_path, '''
        <shape type="sphere">
            <bsdf type="dielectric" id="mat-water">
                <string name="int_ior" value="water"/>
            </bsdf>
        </shape>''')

    _, node = imported_material('mat-water')
    assert node.inputs['IOR'].default_value == pytest.approx(1.333)


def test_import_thindielectric(mi_addon, fresh_scene, tmp_path):
    import_xml(tmp_path, '''
        <shape type="sphere">
            <bsdf type="thindielectric" id="mat-thin"/>
        </shape>''')

    _, node = imported_material('mat-thin')
    assert node.bl_idname == 'ShaderNodeBsdfGlass'
    assert node.inputs['IOR'].default_value == pytest.approx(1.0)


def test_import_roughdielectric(mi_addon, fresh_scene, tmp_path):
    import_xml(tmp_path, '''
        <shape type="sphere">
            <bsdf type="roughdielectric" id="mat-frosted">
                <string name="distribution" value="ggx"/>
                <float name="alpha" value="0.04"/>
                <float name="int_ior" value="1.52"/>
            </bsdf>
        </shape>''')

    _, node = imported_material('mat-frosted')
    assert node.bl_idname == 'ShaderNodeBsdfGlass'
    assert node.distribution == 'GGX'
    assert node.inputs['Roughness'].default_value == pytest.approx(0.2)
    assert node.inputs['IOR'].default_value == pytest.approx(1.52)


def test_import_plastic(mi_addon, fresh_scene, tmp_path):
    import_xml(tmp_path, '''
        <shape type="sphere">
            <bsdf type="plastic" id="mat-shiny">
                <rgb name="diffuse_reflectance" value="0.1 0.2 0.3"/>
            </bsdf>
        </shape>''')

    _, node = imported_material('mat-shiny')
    assert node.bl_idname == 'ShaderNodeBsdfPrincipled'
    assert tuple(node.inputs['Base Color'].default_value) == \
        pytest.approx((0.1, 0.2, 0.3, 1.0))
    assert node.inputs['IOR'].default_value == pytest.approx(1.49)
    assert node.inputs['Roughness'].default_value == 0.0


def test_import_roughplastic(mi_addon, fresh_scene, tmp_path):
    import_xml(tmp_path, '''
        <shape type="sphere">
            <bsdf type="roughplastic" id="mat-matte">
                <float name="alpha" value="0.25"/>
            </bsdf>
        </shape>''')

    _, node = imported_material('mat-matte')
    assert node.bl_idname == 'ShaderNodeBsdfPrincipled'
    assert node.inputs['Roughness'].default_value == pytest.approx(0.5)


###################
##  Round trips  ##
###################

def roundtrip(exporter, tmp_path):
    converter = exporter(tmp_path)
    converter.dict_to_xml(str(tmp_path / 'scene.xml'))
    bpy.ops.wm.read_homefile()
    assert bpy.ops.import_scene.mitsuba(
        filepath=str(tmp_path / 'scene.xml')) == {'FINISHED'}


def test_roundtrip_glass(mi_addon, fresh_scene, exporter, tmp_path):
    node = make_material('ShaderNodeBsdfGlass', name='Glass')
    node.distribution = 'GGX'
    node.inputs['Color'].default_value = (0.9, 0.8, 0.7, 1.0)
    node.inputs['Roughness'].default_value = 0.4
    node.inputs['IOR'].default_value = 1.45

    roundtrip(exporter, tmp_path)
    _, node = imported_material('mat-Glass')
    assert node.bl_idname == 'ShaderNodeBsdfGlass'
    assert node.distribution == 'GGX'
    assert node.inputs['Roughness'].default_value == pytest.approx(0.4)
    assert node.inputs['IOR'].default_value == pytest.approx(1.45)
    assert tuple(node.inputs['Color'].default_value) == \
        pytest.approx((0.9, 0.8, 0.7, 1.0))


def test_roundtrip_glossy(mi_addon, fresh_scene, exporter, tmp_path):
    node = make_material('ShaderNodeBsdfAnisotropic', name='Glossy')
    node.distribution = 'GGX'
    node.inputs['Color'].default_value = (0.9, 0.5, 0.1, 1.0)
    node.inputs['Roughness'].default_value = 0.5

    roundtrip(exporter, tmp_path)
    # The exporter wraps the conductor in twosided; the importer unwraps it
    b_mat = bpy.data.materials['mat-Glossy']
    glossy = [n for n in b_mat.node_tree.nodes
              if n.bl_idname == 'ShaderNodeBsdfAnisotropic']
    assert len(glossy) == 1
    assert glossy[0].distribution == 'GGX'
    assert glossy[0].inputs['Roughness'].default_value == pytest.approx(0.5)
