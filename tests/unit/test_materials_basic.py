"""Tests for the basic BSDF export converters: Glossy, Glass,
Refraction, Transparent and Translucent."""

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
        assert entry['bsdf']['alpha'] == {'type': 'checkerboard'}
    finally:
        del registry._eval._texture_converters['TEX_BRICK']


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

