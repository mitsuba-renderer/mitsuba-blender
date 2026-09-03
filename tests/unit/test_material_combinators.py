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
    converters = registry._resolve._texture_converters
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
    # Mitsuba defaults a shape without a BSDF to a mid-gray diffuse, so an
    # emitter-only material carries its own explicit black diffuse
    assert ctx.data_get('mat-Glow') == {
        'type': 'diffuse',
        'reflectance': {'type': 'rgb', 'value': 0.0},
    }
    assert ctx.exported_mats['mat-Glow'] == {
        'bsdf': 'mat-Glow',
        'emitter': {'type': 'area',
                    'radiance': {'type': 'rgb',
                                 'value': pytest.approx([2.0, 1.0, 0.5])},
                    'twosided': True},
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
    assert 'mat-Dark' not in ctx.exported_mats


def test_emission_strength_graph(fresh_scene, exporter, tmp_path):
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
    assert ctx.exported_mats['mat-MathGlow']['emitter']['radiance'] == \
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
    assert ctx.exported_mats['mat-TexGlow']['emitter'] == \
            {'type': 'area', 'radiance': {'type': 'checkerboard'}, 'twosided' : True}


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
    assert ctx.exported_mats['mat-GlowingDiffuse'] == {
        'bsdf': 'mat-GlowingDiffuse',
        'emitter': {'type': 'area',
                    'radiance': {'type': 'rgb',
                                 'value': pytest.approx([2.0, 1.0, 0.5])},
                    'twosided': True},
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
    assert ctx.exported_mats['mat-DoubleGlow']['emitter']['radiance'] == \
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
    assert ctx.data_get('mat-TwoBsdfs') == registry.ERROR_BSDF


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
    assert ctx.exported_mats['mat-GlowMix']['emitter']['radiance'] == \
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
    assert ctx.data_get('mat-BadMix') == registry.ERROR_BSDF


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


#######################
##   Import  side    ##
#######################

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


def nodes_of_type(b_mat, bl_idname):
    return [n for n in b_mat.node_tree.nodes if n.bl_idname == bl_idname]


def test_import_twosided_single_child(mi_addon, fresh_scene, tmp_path):
    import_xml(tmp_path, '''
        <shape type="sphere">
            <bsdf type="twosided" id="mat-two">
                <bsdf type="diffuse">
                    <rgb name="reflectance" value="0.2 0.4 0.6"/>
                </bsdf>
            </bsdf>
        </shape>''')

    b_mat, node = imported_material('mat-two')
    assert node.bl_idname == 'ShaderNodeBsdfDiffuse'
    assert tuple(node.inputs['Color'].default_value) == \
        pytest.approx((0.2, 0.4, 0.6, 1.0))
    assert len(b_mat.node_tree.nodes) == 2


def test_import_twosided_two_children(mi_addon, fresh_scene, tmp_path):
    import_xml(tmp_path, '''
        <shape type="sphere">
            <bsdf type="twosided" id="mat-frontback">
                <bsdf type="diffuse">
                    <rgb name="reflectance" value="1 0 0"/>
                </bsdf>
                <bsdf type="diffuse">
                    <rgb name="reflectance" value="0 0 1"/>
                </bsdf>
            </bsdf>
        </shape>''')

    b_mat, node = imported_material('mat-frontback')
    assert node.bl_idname == 'ShaderNodeMixShader'
    fac = node.inputs['Fac'].links[0].from_socket
    assert fac.node.bl_idname == 'ShaderNodeNewGeometry'
    assert fac.name == 'Backfacing'
    front = node.inputs[1].links[0].from_node
    back = node.inputs[2].links[0].from_node
    assert tuple(front.inputs['Color'].default_value) == \
        pytest.approx((1.0, 0.0, 0.0, 1.0))
    assert tuple(back.inputs['Color'].default_value) == \
        pytest.approx((0.0, 0.0, 1.0, 1.0))


def test_import_twosided_legacy_child(mi_addon, fresh_scene, tmp_path):
    # The principled importer still lives in the legacy module; the child
    # must be bridged through it without leaving scaffolding behind
    import_xml(tmp_path, '''
        <shape type="sphere">
            <bsdf type="twosided" id="mat-legacy">
                <bsdf type="principled">
                    <rgb name="base_color" value="0.8 0.4 0.2"/>
                </bsdf>
            </bsdf>
        </shape>''')

    b_mat, node = imported_material('mat-legacy')
    assert node.bl_idname == 'ShaderNodeBsdfPrincipled'
    assert tuple(node.inputs['Base Color'].default_value) == \
        pytest.approx((0.8, 0.4, 0.2, 1.0))
    assert nodes_of_type(b_mat, 'NodeReroute') == []


def test_import_blendbsdf(mi_addon, fresh_scene, tmp_path):
    import_xml(tmp_path, '''
        <shape type="sphere">
            <bsdf type="blendbsdf" id="mat-blend">
                <float name="weight" value="0.3"/>
                <bsdf type="diffuse">
                    <rgb name="reflectance" value="1 0 0"/>
                </bsdf>
                <bsdf type="diffuse">
                    <rgb name="reflectance" value="0 0 1"/>
                </bsdf>
            </bsdf>
        </shape>''')

    _, node = imported_material('mat-blend')
    assert node.bl_idname == 'ShaderNodeMixShader'
    assert node.inputs['Fac'].default_value == pytest.approx(0.3)
    first = node.inputs[1].links[0].from_node
    second = node.inputs[2].links[0].from_node
    assert tuple(first.inputs['Color'].default_value) == \
        pytest.approx((1.0, 0.0, 0.0, 1.0))
    assert tuple(second.inputs['Color'].default_value) == \
        pytest.approx((0.0, 0.0, 1.0, 1.0))


def test_import_mask_black_diffuse(mi_addon, fresh_scene, tmp_path):
    import_xml(tmp_path, '''
        <shape type="sphere">
            <bsdf type="mask" id="mat-glass">
                <float name="opacity" value="0.3"/>
                <bsdf type="diffuse">
                    <rgb name="reflectance" value="0 0 0"/>
                </bsdf>
            </bsdf>
        </shape>''')

    b_mat, node = imported_material('mat-glass')
    assert node.bl_idname == 'ShaderNodeBsdfTransparent'
    assert tuple(node.inputs['Color'].default_value) == \
        pytest.approx((0.7, 0.7, 0.7, 1.0))
    assert len(b_mat.node_tree.nodes) == 2


def test_import_mask_general(mi_addon, fresh_scene, tmp_path):
    import_xml(tmp_path, '''
        <shape type="sphere">
            <bsdf type="mask" id="mat-masked">
                <float name="opacity" value="0.4"/>
                <bsdf type="diffuse">
                    <rgb name="reflectance" value="0.2 0.4 0.6"/>
                </bsdf>
            </bsdf>
        </shape>''')

    _, node = imported_material('mat-masked')
    assert node.bl_idname == 'ShaderNodeMixShader'
    assert node.inputs['Fac'].default_value == pytest.approx(0.4)
    assert node.inputs[1].links[0].from_node.bl_idname == \
        'ShaderNodeBsdfTransparent'
    diffuse = node.inputs[2].links[0].from_node
    assert tuple(diffuse.inputs['Color'].default_value) == \
        pytest.approx((0.2, 0.4, 0.6, 1.0))


def test_import_null(mi_addon, fresh_scene, tmp_path):
    import_xml(tmp_path, '''
        <shape type="sphere">
            <bsdf type="null" id="mat-invisible"/>
        </shape>''')

    b_mat, node = imported_material('mat-invisible')
    assert node.bl_idname == 'ShaderNodeBsdfTransparent'
    assert len(b_mat.node_tree.nodes) == 2


####################
##   Roundtrips   ##
####################

def roundtrip(exporter, tmp_path):
    converter = exporter(tmp_path)
    converter.dict_to_xml(str(tmp_path / 'scene.xml'))
    bpy.ops.wm.read_homefile()
    assert bpy.ops.import_scene.mitsuba(
        filepath=str(tmp_path / 'scene.xml')) == {'FINISHED'}


def test_roundtrip_mix(mi_addon, fresh_scene, exporter, tmp_path):
    b_mat = make_material('Blend')
    mix = b_mat.node_tree.nodes.new('ShaderNodeMixShader')
    mix.inputs['Fac'].default_value = 0.3
    first = add_diffuse(b_mat, color=(1.0, 0.0, 0.0, 1.0))
    second = add_diffuse(b_mat, color=(0.0, 0.0, 1.0, 1.0))
    b_mat.node_tree.links.new(first.outputs['BSDF'], mix.inputs[1])
    b_mat.node_tree.links.new(second.outputs['BSDF'], mix.inputs[2])
    link_surface(b_mat, mix.outputs['Shader'])
    assign_material(b_mat)

    roundtrip(exporter, tmp_path)
    _, node = imported_material('mat-Blend')
    assert node.bl_idname == 'ShaderNodeMixShader'
    assert node.inputs['Fac'].default_value == pytest.approx(0.3)
    first = node.inputs[1].links[0].from_node
    second = node.inputs[2].links[0].from_node
    assert tuple(first.inputs['Color'].default_value) == \
        pytest.approx((1.0, 0.0, 0.0, 1.0))
    assert tuple(second.inputs['Color'].default_value) == \
        pytest.approx((0.0, 0.0, 1.0, 1.0))


def test_roundtrip_mask(mi_addon, fresh_scene, exporter, tmp_path):
    b_mat = make_material('Masked')
    mix = b_mat.node_tree.nodes.new('ShaderNodeMixShader')
    mix.inputs['Fac'].default_value = 0.7
    transparent = b_mat.node_tree.nodes.new('ShaderNodeBsdfTransparent')
    b_mat.node_tree.links.new(transparent.outputs['BSDF'], mix.inputs[1])
    diffuse = add_diffuse(b_mat)
    b_mat.node_tree.links.new(diffuse.outputs['BSDF'], mix.inputs[2])
    link_surface(b_mat, mix.outputs['Shader'])
    assign_material(b_mat)

    roundtrip(exporter, tmp_path)
    _, node = imported_material('mat-Masked')
    assert node.bl_idname == 'ShaderNodeMixShader'
    assert node.inputs['Fac'].default_value == pytest.approx(0.7)
    assert node.inputs[1].links[0].from_node.bl_idname == \
        'ShaderNodeBsdfTransparent'
    diffuse = node.inputs[2].links[0].from_node
    assert tuple(diffuse.inputs['Color'].default_value) == \
        pytest.approx((0.2, 0.4, 0.6, 1.0))


def test_roundtrip_emission(mi_addon, fresh_scene, exporter, tmp_path):
    b_mat = make_material('Glow')
    link_surface(b_mat, add_emission(b_mat).outputs['Emission'])
    assign_material(b_mat)

    roundtrip(exporter, tmp_path)
    # An emitter-only material is exported as a black BSDF under the material
    # id plus an area emitter on the shape
    b_mat, node = imported_material('mat-Glow')
    assert node.bl_idname == 'ShaderNodeAddShader'
    emission = nodes_of_type(b_mat, 'ShaderNodeEmission')
    assert len(emission) == 1
    assert emission[0].inputs['Strength'].default_value == pytest.approx(2.0)
    assert tuple(emission[0].inputs['Color'].default_value) == \
        pytest.approx((1.0, 0.5, 0.25, 1.0))
