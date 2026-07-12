"""Tests for the shader combinator converters (Mix, Add, Emission, Holdout)."""

import contextlib
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


@contextlib.contextmanager
def fake_texture_converter(registry, node_type, params):
    """Temporarily registers a texture converter, restoring any previous one."""
    converters = registry._eval._texture_converters
    previous = converters.get(node_type)
    converters[node_type] = lambda export_ctx, node, out_socket: dict(params)
    try:
        yield
    finally:
        if previous is None:
            del converters[node_type]
        else:
            converters[node_type] = previous


def make_material(name):
    b_mat = bpy.data.materials.new(name)
    b_mat.use_nodes = True
    tree = b_mat.node_tree
    tree.nodes.remove(tree.nodes['Principled BSDF'])
    return b_mat


def link_surface(b_mat, out_socket):
    tree = b_mat.node_tree
    tree.links.new(out_socket,
                   tree.nodes['Material Output'].inputs['Surface'])


def add_diffuse(b_mat, color=(0.2, 0.4, 0.6, 1.0)):
    node = b_mat.node_tree.nodes.new('ShaderNodeBsdfDiffuse')
    node.inputs['Color'].default_value = color
    return node


def add_emission(b_mat, color=(1.0, 0.5, 0.25, 1.0), strength=2.0):
    node = b_mat.node_tree.nodes.new('ShaderNodeEmission')
    node.inputs['Color'].default_value = color
    node.inputs['Strength'].default_value = strength
    return node


def assign_material(b_mat, object_name='Cube'):
    b_obj = bpy.data.objects[object_name]
    b_obj.data.materials.clear()
    b_obj.data.materials.append(b_mat)


def diffuse_dict(color):
    return {
        'type': 'twosided',
        'bsdf': {
            'type': 'diffuse',
            'reflectance': {'type': 'rgb', 'value': pytest.approx(color)},
        },
    }


##################
##   Emission   ##
##################

def test_emission_export(fresh_scene, exporter, tmp_path):
    b_mat = make_material('Glow')
    link_surface(b_mat, add_emission(b_mat).outputs['Emission'])
    assign_material(b_mat)

    converter = exporter(tmp_path)
    ctx = converter.export_ctx
    assert ctx.data_get('mat-Glow') is None
    assert ctx.data_get('empty-emitter-bsdf') is not None
    assert ctx.exported_mats.mats['mat-Glow'] == {
        'bsdf': 'empty-emitter-bsdf',
        'emitter': {'type': 'area',
                    'radiance': {'type': 'rgb',
                                 'value': pytest.approx([2.0, 1.0, 0.5])}},
    }

    # The render-mode scene dict must load, emitter and shape included
    import mitsuba as mi
    converter = exporter(tmp_path, render=True)
    assert mi.load_dict(converter.export_ctx.scene_data) is not None


def test_emission_zero_strength_exports_black_diffuse(fresh_scene, exporter,
                                                      tmp_path):
    b_mat = make_material('Dark')
    link_surface(b_mat, add_emission(b_mat, strength=0.0).outputs['Emission'])
    assign_material(b_mat)

    ctx = exporter(tmp_path).export_ctx
    assert ctx.data_get('mat-Dark') == {
        'type': 'diffuse',
        'reflectance': {'type': 'rgb', 'value': 0.0},
    }
    assert not ctx.exported_mats.has_mat('mat-Dark')


def test_emission_folds_strength_graph(fresh_scene, exporter, tmp_path):
    b_mat = make_material('MathGlow')
    emission = add_emission(b_mat, color=(1.0, 1.0, 1.0, 1.0))
    math_node = b_mat.node_tree.nodes.new('ShaderNodeMath')
    math_node.operation = 'MULTIPLY'
    math_node.inputs[0].default_value = 3.0
    math_node.inputs[1].default_value = 0.5
    b_mat.node_tree.links.new(math_node.outputs['Value'],
                              emission.inputs['Strength'])
    link_surface(b_mat, emission.outputs['Emission'])
    assign_material(b_mat)

    ctx = exporter(tmp_path).export_ctx
    assert ctx.exported_mats.mats['mat-MathGlow']['emitter']['radiance'] == \
        {'type': 'rgb', 'value': pytest.approx([1.5, 1.5, 1.5])}


def test_emission_textured_color(fresh_scene, exporter, tmp_path, registry):
    b_mat = make_material('TexGlow')
    emission = add_emission(b_mat, strength=1.0)
    noise = b_mat.node_tree.nodes.new('ShaderNodeTexNoise')
    b_mat.node_tree.links.new(noise.outputs['Color'],
                              emission.inputs['Color'])
    link_surface(b_mat, emission.outputs['Emission'])
    assign_material(b_mat)

    with fake_texture_converter(registry, 'TEX_NOISE',
                                {'type': 'checkerboard'}):
        ctx = exporter(tmp_path).export_ctx
    assert ctx.exported_mats.mats['mat-TexGlow']['emitter'] == \
        {'type': 'area', 'radiance': {'type': 'checkerboard'}}


###################
##   Add Shader  ##
###################

def test_add_emission_and_bsdf(fresh_scene, exporter, tmp_path):
    b_mat = make_material('GlowingDiffuse')
    add = b_mat.node_tree.nodes.new('ShaderNodeAddShader')
    b_mat.node_tree.links.new(add_emission(b_mat).outputs['Emission'],
                              add.inputs[0])
    b_mat.node_tree.links.new(add_diffuse(b_mat).outputs['BSDF'],
                              add.inputs[1])
    link_surface(b_mat, add.outputs['Shader'])
    assign_material(b_mat)

    ctx = exporter(tmp_path).export_ctx
    assert ctx.data_get('mat-GlowingDiffuse') == diffuse_dict([0.2, 0.4, 0.6])
    assert ctx.exported_mats.mats['mat-GlowingDiffuse'] == {
        'bsdf': 'mat-GlowingDiffuse',
        'emitter': {'type': 'area',
                    'radiance': {'type': 'rgb',
                                 'value': pytest.approx([2.0, 1.0, 0.5])}},
    }


def test_add_two_emissions_sums_radiance(fresh_scene, exporter, tmp_path):
    b_mat = make_material('DoubleGlow')
    add = b_mat.node_tree.nodes.new('ShaderNodeAddShader')
    first = add_emission(b_mat, color=(1.0, 0.0, 0.0, 1.0), strength=1.0)
    second = add_emission(b_mat, color=(0.0, 1.0, 0.0, 1.0), strength=3.0)
    b_mat.node_tree.links.new(first.outputs['Emission'], add.inputs[0])
    b_mat.node_tree.links.new(second.outputs['Emission'], add.inputs[1])
    link_surface(b_mat, add.outputs['Shader'])
    assign_material(b_mat)

    ctx = exporter(tmp_path).export_ctx
    assert ctx.exported_mats.mats['mat-DoubleGlow']['emitter']['radiance'] == \
        {'type': 'rgb', 'value': pytest.approx([1.0, 3.0, 0.0])}


def test_add_two_bsdfs_falls_back(fresh_scene, exporter, tmp_path, registry):
    b_mat = make_material('TwoBsdfs')
    add = b_mat.node_tree.nodes.new('ShaderNodeAddShader')
    b_mat.node_tree.links.new(add_diffuse(b_mat).outputs['BSDF'],
                              add.inputs[0])
    b_mat.node_tree.links.new(add_diffuse(b_mat).outputs['BSDF'],
                              add.inputs[1])
    link_surface(b_mat, add.outputs['Shader'])
    assign_material(b_mat)

    ctx = exporter(tmp_path).export_ctx
    assert ctx.data_get('mat-TwoBsdfs') == registry.FALLBACK_BSDF


###################
##   Mix Shader  ##
###################

def test_mix_two_bsdfs_constant_factor(fresh_scene, exporter, tmp_path):
    b_mat = make_material('Blend')
    mix = b_mat.node_tree.nodes.new('ShaderNodeMixShader')
    mix.inputs['Fac'].default_value = 0.3
    first = add_diffuse(b_mat, color=(1.0, 0.0, 0.0, 1.0))
    second = add_diffuse(b_mat, color=(0.0, 0.0, 1.0, 1.0))
    b_mat.node_tree.links.new(first.outputs['BSDF'], mix.inputs[1])
    b_mat.node_tree.links.new(second.outputs['BSDF'], mix.inputs[2])
    link_surface(b_mat, mix.outputs['Shader'])
    assign_material(b_mat)

    ctx = exporter(tmp_path).export_ctx
    entry = ctx.data_get('mat-Blend')
    assert entry['type'] == 'blendbsdf'
    assert entry['weight'] == pytest.approx(0.3)
    assert entry['bsdf1'] == diffuse_dict([1.0, 0.0, 0.0])
    assert entry['bsdf2'] == diffuse_dict([0.0, 0.0, 1.0])

    import mitsuba as mi
    assert mi.load_dict(entry) is not None


def test_mix_two_bsdfs_textured_factor(fresh_scene, exporter, tmp_path,
                                       registry):
    b_mat = make_material('TexBlend')
    mix = b_mat.node_tree.nodes.new('ShaderNodeMixShader')
    noise = b_mat.node_tree.nodes.new('ShaderNodeTexNoise')
    b_mat.node_tree.links.new(noise.outputs['Fac'], mix.inputs['Fac'])
    b_mat.node_tree.links.new(add_diffuse(b_mat).outputs['BSDF'],
                              mix.inputs[1])
    b_mat.node_tree.links.new(add_diffuse(b_mat).outputs['BSDF'],
                              mix.inputs[2])
    link_surface(b_mat, mix.outputs['Shader'])
    assign_material(b_mat)

    with fake_texture_converter(registry, 'TEX_NOISE',
                                {'type': 'checkerboard'}):
        ctx = exporter(tmp_path).export_ctx
    assert ctx.data_get('mat-TexBlend')['weight'] == {'type': 'checkerboard'}


def test_mix_two_emissions(fresh_scene, exporter, tmp_path):
    b_mat = make_material('GlowMix')
    mix = b_mat.node_tree.nodes.new('ShaderNodeMixShader')
    mix.inputs['Fac'].default_value = 0.25
    first = add_emission(b_mat, color=(1.0, 0.0, 0.0, 1.0), strength=1.0)
    second = add_emission(b_mat, color=(0.0, 1.0, 0.0, 1.0), strength=2.0)
    b_mat.node_tree.links.new(first.outputs['Emission'], mix.inputs[1])
    b_mat.node_tree.links.new(second.outputs['Emission'], mix.inputs[2])
    link_surface(b_mat, mix.outputs['Shader'])
    assign_material(b_mat)

    ctx = exporter(tmp_path).export_ctx
    assert ctx.exported_mats.mats['mat-GlowMix']['emitter']['radiance'] == \
        {'type': 'rgb', 'value': pytest.approx([0.75, 0.5, 0.0])}


def test_mix_bsdf_with_emission_falls_back(fresh_scene, exporter, tmp_path,
                                           registry):
    b_mat = make_material('BadMix')
    mix = b_mat.node_tree.nodes.new('ShaderNodeMixShader')
    b_mat.node_tree.links.new(add_emission(b_mat).outputs['Emission'],
                              mix.inputs[1])
    b_mat.node_tree.links.new(add_diffuse(b_mat).outputs['BSDF'],
                              mix.inputs[2])
    link_surface(b_mat, mix.outputs['Shader'])
    assign_material(b_mat)

    ctx = exporter(tmp_path).export_ctx
    assert ctx.data_get('mat-BadMix') == registry.FALLBACK_BSDF


def test_mix_transparent_first_exports_mask(fresh_scene, exporter, tmp_path):
    b_mat = make_material('Masked')
    mix = b_mat.node_tree.nodes.new('ShaderNodeMixShader')
    mix.inputs['Fac'].default_value = 0.7
    transparent = b_mat.node_tree.nodes.new('ShaderNodeBsdfTransparent')
    b_mat.node_tree.links.new(transparent.outputs['BSDF'], mix.inputs[1])
    b_mat.node_tree.links.new(add_diffuse(b_mat).outputs['BSDF'],
                              mix.inputs[2])
    link_surface(b_mat, mix.outputs['Shader'])
    assign_material(b_mat)

    ctx = exporter(tmp_path).export_ctx
    entry = ctx.data_get('mat-Masked')
    assert entry['type'] == 'mask'
    assert entry['opacity'] == pytest.approx(0.7)
    assert entry['bsdf'] == diffuse_dict([0.2, 0.4, 0.6])

    import mitsuba as mi
    assert mi.load_dict(entry) is not None


def test_mix_transparent_second_inverts_opacity(fresh_scene, exporter,
                                                tmp_path):
    b_mat = make_material('MaskedInv')
    mix = b_mat.node_tree.nodes.new('ShaderNodeMixShader')
    mix.inputs['Fac'].default_value = 0.7
    transparent = b_mat.node_tree.nodes.new('ShaderNodeBsdfTransparent')
    b_mat.node_tree.links.new(add_diffuse(b_mat).outputs['BSDF'],
                              mix.inputs[1])
    b_mat.node_tree.links.new(transparent.outputs['BSDF'], mix.inputs[2])
    link_surface(b_mat, mix.outputs['Shader'])
    assign_material(b_mat)

    entry = exporter(tmp_path).export_ctx.data_get('mat-MaskedInv')
    assert entry['type'] == 'mask'
    assert entry['opacity'] == pytest.approx(0.3)


def test_mix_transparent_textured_factor_uses_blend(fresh_scene, exporter,
                                                    tmp_path, registry):
    b_mat = make_material('MaskedTex')
    mix = b_mat.node_tree.nodes.new('ShaderNodeMixShader')
    noise = b_mat.node_tree.nodes.new('ShaderNodeTexNoise')
    b_mat.node_tree.links.new(noise.outputs['Fac'], mix.inputs['Fac'])
    transparent = b_mat.node_tree.nodes.new('ShaderNodeBsdfTransparent')
    b_mat.node_tree.links.new(add_diffuse(b_mat).outputs['BSDF'],
                              mix.inputs[1])
    b_mat.node_tree.links.new(transparent.outputs['BSDF'], mix.inputs[2])
    link_surface(b_mat, mix.outputs['Shader'])
    assign_material(b_mat)

    with fake_texture_converter(registry, 'TEX_NOISE',
                                {'type': 'checkerboard'}):
        ctx = exporter(tmp_path).export_ctx
    entry = ctx.data_get('mat-MaskedTex')
    assert entry['type'] == 'blendbsdf'
    assert entry['weight'] == {'type': 'checkerboard'}
    assert entry['bsdf1'] == diffuse_dict([0.2, 0.4, 0.6])
    assert entry['bsdf2'] == {'type': 'null'}


################
##   Holdout  ##
################

def test_holdout_exports_null(fresh_scene, exporter, tmp_path):
    b_mat = make_material('Hold')
    holdout = b_mat.node_tree.nodes.new('ShaderNodeHoldout')
    link_surface(b_mat, holdout.outputs['Holdout'])
    assign_material(b_mat)

    ctx = exporter(tmp_path).export_ctx
    assert ctx.data_get('mat-Hold') == {'type': 'null'}
