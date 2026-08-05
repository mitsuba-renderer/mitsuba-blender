"""Tests for the material converter registries (export and import)."""

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


def make_diffuse_material(name='Diffuse', color=(0.2, 0.4, 0.6, 1.0)):
    b_mat = bpy.data.materials.new(name)
    b_mat.use_nodes = True
    tree = b_mat.node_tree
    tree.nodes.remove(tree.nodes['Principled BSDF'])
    diffuse = tree.nodes.new('ShaderNodeBsdfDiffuse')
    diffuse.inputs['Color'].default_value = color
    tree.links.new(diffuse.outputs['BSDF'],
                   tree.nodes['Material Output'].inputs['Surface'])
    return b_mat


def assign_material(b_mat, object_name='Cube'):
    b_obj = bpy.data.objects[object_name]
    b_obj.data.materials.clear()
    b_obj.data.materials.append(b_mat)


def test_diffuse_export(fresh_scene, exporter, tmp_path):
    b_mat = make_diffuse_material()
    assign_material(b_mat)

    converter = exporter(tmp_path)
    entry = converter.export_ctx.data_get('mat-Diffuse')
    assert entry == {
        'type': 'twosided',
        'bsdf': {
            'type': 'diffuse',
            'reflectance': {'type': 'rgb',
                            'value': pytest.approx([0.2, 0.4, 0.6])},
        },
    }

    import mitsuba as mi
    assert mi.load_dict(entry) is not None


def test_diffuse_export_folds_input_graph(fresh_scene, exporter, tmp_path):
    b_mat = make_diffuse_material()
    tree = b_mat.node_tree
    diffuse = tree.nodes['Diffuse BSDF']
    mix = tree.nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    a_color = next(s for s in mix.inputs if s.identifier == 'A_Color')
    b_color = next(s for s in mix.inputs if s.identifier == 'B_Color')
    factor = next(s for s in mix.inputs if s.identifier == 'Factor_Float')
    a_color.default_value = (1.0, 0.0, 0.0, 1.0)
    b_color.default_value = (0.0, 0.0, 1.0, 1.0)
    factor.default_value = 0.25
    result = next(s for s in mix.outputs if s.identifier == 'Result_Color')
    tree.links.new(result, diffuse.inputs['Color'])
    assign_material(b_mat)

    converter = exporter(tmp_path)
    entry = converter.export_ctx.data_get('mat-Diffuse')
    assert entry['bsdf']['reflectance']['value'] == \
        pytest.approx([0.75, 0.0, 0.25])


def test_default_principled_material(fresh_scene, exporter, tmp_path):
    # The default cube material is a Principled BSDF
    converter = exporter(tmp_path)
    entry = converter.export_ctx.data_get('mat-Material')
    assert entry['type'] == 'twosided'
    assert entry['bsdf']['type'] == 'principled'


def test_unlinked_surface_exports_fallback(fresh_scene, exporter, tmp_path,
                                           registry):
    b_mat = bpy.data.materials.new('Unlinked')
    b_mat.use_nodes = True
    tree = b_mat.node_tree
    for link in list(tree.links):
        tree.links.remove(link)
    assign_material(b_mat)

    converter = exporter(tmp_path)
    entry = converter.export_ctx.data_get('mat-Unlinked')
    assert entry == registry.ERROR_BSDF
    assert entry is not registry.ERROR_BSDF


def test_converter_error_boundary(fresh_scene, exporter, tmp_path, registry):
    @registry.node_converter('BSDF_TOON')
    def convert_toon(export_ctx, node):
        raise registry.ConversionError('toon says no')

    try:
        b_mat = make_diffuse_material('Toon')
        tree = b_mat.node_tree
        tree.nodes.remove(tree.nodes['Diffuse BSDF'])
        toon = tree.nodes.new('ShaderNodeBsdfToon')
        tree.links.new(toon.outputs['BSDF'],
                       tree.nodes['Material Output'].inputs['Surface'])
        assign_material(b_mat)

        converter = exporter(tmp_path)
        entry = converter.export_ctx.data_get('mat-Toon')
        assert entry == registry.ERROR_BSDF
    finally:
        del registry._node_converters['BSDF_TOON']


def test_has_converter(fresh_scene, registry):
    b_mat = make_diffuse_material('Sheen')
    tree = b_mat.node_tree
    tree.nodes.remove(tree.nodes['Diffuse BSDF'])
    sheen = tree.nodes.new('ShaderNodeBsdfSheen')
    tree.links.new(sheen.outputs['BSDF'],
                   tree.nodes['Material Output'].inputs['Surface'])
    assert not registry.has_converter(b_mat)

    assert registry.has_converter(make_diffuse_material('ForRegistry'))

    no_nodes = bpy.data.materials.new('NoNodes')
    assert not registry.has_converter(no_nodes)


def test_add_material_to_dict_layouts(mi_addon, registry):
    materials = registry
    export_context = sys.modules[mi_addon].io.exporter.export_context

    bsdf = {'type': 'diffuse'}
    emitter = {'type': 'area', 'radiance': {'type': 'rgb', 'value': [1, 1, 1]}}

    # BSDF only: stored under the material id
    ctx = export_context.ExportContext()
    materials.add_material_to_dict(ctx, 'mat-a', dict(bsdf), None)
    assert ctx.data_get('mat-a') == bsdf
    assert 'mat-a' not in ctx.exported_mats

    # BSDF and emitter: BSDF in the dict, pair in the cache
    ctx = export_context.ExportContext()
    materials.add_material_to_dict(ctx, 'mat-b', dict(bsdf), dict(emitter))
    assert ctx.data_get('mat-b') == bsdf
    assert ctx.exported_mats['mat-b'] == {'bsdf': 'mat-b',
                                               'emitter': emitter}

    # Emitter only: shared black BSDF
    ctx = export_context.ExportContext()
    materials.add_material_to_dict(ctx, 'mat-c', None, dict(emitter))
    assert ctx.data_get('empty-emitter-bsdf') is not None
    assert ctx.exported_mats['mat-c']['bsdf'] == 'empty-emitter-bsdf'


def test_shared_material_exported_once(fresh_scene, exporter, tmp_path):
    b_mat = make_diffuse_material('Shared')
    assign_material(b_mat)
    bpy.ops.mesh.primitive_cube_add(location=(4, 0, 0))
    bpy.context.active_object.data.materials.append(b_mat)

    converter = exporter(tmp_path)
    entries = [key for key in converter.export_ctx.scene_data
               if key.startswith('mat-Shared')]
    assert entries == ['mat-Shared']


#######################
##   Import  side    ##
#######################

@pytest.fixture(scope='session')
def import_registry(mi_addon):
    return importlib.import_module(f'{mi_addon}.convert.importer.materials')


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


def test_import_diffuse(mi_addon, fresh_scene, tmp_path):
    import_xml(tmp_path, '''
        <shape type="sphere">
            <bsdf type="diffuse" id="mat-thing">
                <rgb name="reflectance" value="0.2 0.4 0.6"/>
            </bsdf>
        </shape>''')

    b_mat, node = imported_material('mat-thing')
    assert node.bl_idname == 'ShaderNodeBsdfDiffuse'
    assert tuple(node.inputs['Color'].default_value) == \
        pytest.approx((0.2, 0.4, 0.6, 1.0))


def test_import_diffuse_default_reflectance(mi_addon, fresh_scene, tmp_path):
    import_xml(tmp_path, '''
        <shape type="sphere">
            <bsdf type="diffuse" id="mat-plain"/>
        </shape>''')

    _, node = imported_material('mat-plain')
    assert node.bl_idname == 'ShaderNodeBsdfDiffuse'
    assert tuple(node.inputs['Color'].default_value) == \
        pytest.approx((0.8, 0.8, 0.8, 1.0))


def test_import_diffuse_with_emitter(mi_addon, fresh_scene, tmp_path):
    import_xml(tmp_path, '''
        <shape type="rectangle">
            <bsdf type="diffuse" id="mat-glowing"/>
            <emitter type="area">
                <rgb name="radiance" value="3 3 3"/>
            </emitter>
        </shape>''')

    b_mat, node = imported_material('mat-glowing')
    assert node.bl_idname == 'ShaderNodeAddShader'
    tree = b_mat.node_tree
    emission = [n for n in tree.nodes
                if n.bl_idname == 'ShaderNodeEmission']
    assert len(emission) == 1
    assert emission[0].inputs['Strength'].default_value == \
        pytest.approx(3.0)
    diffuse = [n for n in tree.nodes
               if n.bl_idname == 'ShaderNodeBsdfDiffuse']
    assert len(diffuse) == 1


def test_import_error_placeholder(mi_addon, fresh_scene, tmp_path,
                                  import_registry):
    previous = import_registry._material_converters.get('plastic')

    @import_registry.material_converter('plastic')
    def convert_plastic(builder, mi_props):
        raise import_registry.ConversionError('plastic says no')

    try:
        import_xml(tmp_path, '''
            <shape type="sphere">
                <bsdf type="plastic" id="mat-broken"/>
            </shape>''')
    finally:
        if previous is None:
            del import_registry._material_converters['plastic']
        else:
            import_registry._material_converters['plastic'] = previous

    _, node = imported_material('mat-broken')
    assert node.bl_idname == 'ShaderNodeBsdfDiffuse'
    assert tuple(node.inputs['Color'].default_value) == \
        pytest.approx(import_registry.ERROR_COLOR)


def test_roundtrip_diffuse(mi_addon, fresh_scene, exporter, tmp_path):
    b_mat = make_diffuse_material('Roundtrip', color=(0.25, 0.5, 0.75, 1.0))
    assign_material(b_mat)
    converter = exporter(tmp_path)
    converter.dict_to_xml(str(tmp_path / 'scene.xml'))

    bpy.ops.wm.read_homefile()
    assert bpy.ops.import_scene.mitsuba(
        filepath=str(tmp_path / 'scene.xml')) == {'FINISHED'}
    # The exporter wraps the diffuse BSDF in twosided, which the legacy
    # importer unwraps before dispatching the inner diffuse
    b_mat = bpy.data.materials['mat-Roundtrip']
    diffuse = [n for n in b_mat.node_tree.nodes
               if n.bl_idname == 'ShaderNodeBsdfDiffuse']
    assert len(diffuse) == 1
    assert tuple(diffuse[0].inputs['Color'].default_value) == \
        pytest.approx((0.25, 0.5, 0.75, 1.0))
