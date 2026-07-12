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


def test_principled_still_uses_old_path(fresh_scene, exporter, tmp_path):
    # The default cube material is a Principled BSDF, which has no
    # registered converter yet
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
    assert entry == registry.FALLBACK_BSDF
    assert entry is not registry.FALLBACK_BSDF


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
        assert entry == registry.FALLBACK_BSDF
    finally:
        del registry._node_converters['BSDF_TOON']


def test_has_converter(fresh_scene, registry):
    b_mat = make_diffuse_material('Glass')
    tree = b_mat.node_tree
    tree.nodes.remove(tree.nodes['Diffuse BSDF'])
    glass = tree.nodes.new('ShaderNodeBsdfGlass')
    tree.links.new(glass.outputs['BSDF'],
                   tree.nodes['Material Output'].inputs['Surface'])
    assert not registry.has_converter(b_mat)

    assert registry.has_converter(make_diffuse_material('ForRegistry'))

    no_nodes = bpy.data.materials.new('NoNodes')
    assert not registry.has_converter(no_nodes)


def test_add_material_to_dict_layouts(mi_addon):
    materials = sys.modules[mi_addon].io.exporter.materials
    export_context = sys.modules[mi_addon].io.exporter.export_context

    bsdf = {'type': 'diffuse'}
    emitter = {'type': 'area', 'radiance': {'type': 'rgb', 'value': [1, 1, 1]}}

    # BSDF only: stored under the material id
    ctx = export_context.ExportContext()
    materials.add_material_to_dict(ctx, 'mat-a', dict(bsdf), None)
    assert ctx.data_get('mat-a') == bsdf
    assert not ctx.exported_mats.has_mat('mat-a')

    # BSDF and emitter: BSDF in the dict, pair in the cache
    ctx = export_context.ExportContext()
    materials.add_material_to_dict(ctx, 'mat-b', dict(bsdf), dict(emitter))
    assert ctx.data_get('mat-b') == bsdf
    assert ctx.exported_mats.mats['mat-b'] == {'bsdf': 'mat-b',
                                               'emitter': emitter}

    # Emitter only: shared black BSDF
    ctx = export_context.ExportContext()
    materials.add_material_to_dict(ctx, 'mat-c', None, dict(emitter))
    assert ctx.data_get('empty-emitter-bsdf') is not None
    assert ctx.exported_mats.mats['mat-c']['bsdf'] == 'empty-emitter-bsdf'


def test_shared_material_exported_once(fresh_scene, exporter, tmp_path):
    b_mat = make_diffuse_material('Shared')
    assign_material(b_mat)
    bpy.ops.mesh.primitive_cube_add(location=(4, 0, 0))
    bpy.context.active_object.data.materials.append(b_mat)

    converter = exporter(tmp_path)
    entries = [key for key in converter.export_ctx.scene_data
               if key.startswith('mat-Shared')]
    assert entries == ['mat-Shared']
