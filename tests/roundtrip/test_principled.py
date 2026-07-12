"""Roundtrip tests for Principled BSDF materials."""

import importlib
import sys

import bpy
import pytest


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


def principled_node(name='Material'):
    return bpy.data.materials[name].node_tree.nodes['Principled BSDF']


def surface_node(b_mat):
    surface = b_mat.node_tree.get_output_node('CYCLES').inputs['Surface']
    assert surface.is_linked
    return surface.links[0].from_node


def test_roundtrip_transmissive(mi_addon, fresh_scene, exporter, tmp_path):
    node = principled_node()
    node.inputs['Base Color'].default_value = (0.2, 0.4, 0.6, 1.0)
    node.inputs['Roughness'].default_value = 0.2
    node.inputs['Transmission Weight'].default_value = 1.0
    node.inputs['IOR'].default_value = 1.33

    converter = exporter(tmp_path)
    converter.dict_to_xml(str(tmp_path / 'scene.xml'))
    bpy.ops.wm.read_homefile()
    assert bpy.ops.import_scene.mitsuba(
        filepath=str(tmp_path / 'scene.xml')) == {'FINISHED'}

    node = surface_node(bpy.data.materials['mat-Material'])
    assert node.bl_idname == 'ShaderNodeBsdfPrincipled'
    assert tuple(node.inputs['Base Color'].default_value) == \
        pytest.approx((0.2, 0.4, 0.6, 1.0))
    assert node.inputs['Roughness'].default_value == pytest.approx(0.2)
    assert node.inputs['Transmission Weight'].default_value == \
        pytest.approx(1.0)
    assert node.inputs['IOR'].default_value == pytest.approx(1.33)


def test_roundtrip_reflective_through_registries(mi_addon, fresh_scene,
                                                 exporter, tmp_path):
    """Export dict -> mi parser -> import registry, without the legacy
    twosided unwrapping in between."""
    import mitsuba as mi

    node = principled_node()
    node.inputs['Base Color'].default_value = (0.6, 0.3, 0.1, 1.0)
    node.inputs['Roughness'].default_value = 0.3
    node.inputs['Metallic'].default_value = 0.6
    node.inputs['Anisotropic'].default_value = 0.4
    node.inputs['Specular IOR Level'].default_value = 0.4
    node.inputs['Sheen Weight'].default_value = 0.3
    node.inputs['Coat Weight'].default_value = 0.5
    node.inputs['Coat Roughness'].default_value = 0.1

    converter = exporter(tmp_path)
    entry = converter.export_ctx.data_get('mat-Material')
    assert entry['type'] == 'twosided'

    state = mi.parser.parse_dict(mi.parser.ParserConfig(mi.variant()),
                                 {'type': 'scene', 'mat': entry})
    mi_props = next(n.props for n in state.nodes
                    if n.props.plugin_name() == 'principled')

    class StubContext:
        mi_state = state

        def log(self, message, level='INFO'):
            pass

    importer = importlib.import_module(
        f'{mi_addon}.convert.importer.materials')
    b_mat = importer.convert_material(StubContext(), mi_props)

    imported = surface_node(b_mat)
    assert imported.bl_idname == 'ShaderNodeBsdfPrincipled'
    for socket_name, expected in [
            ('Base Color', (0.6, 0.3, 0.1, 1.0)),
            ('Roughness', 0.3),
            ('Metallic', 0.6),
            ('Anisotropic', 0.4),
            ('Specular IOR Level', 0.4),
            ('Sheen Weight', 0.3),
            ('Coat Weight', 0.5),
            ('Coat Roughness', 0.1)]:
        value = imported.inputs[socket_name].default_value
        if isinstance(expected, tuple):
            value = tuple(value)
        assert value == pytest.approx(expected, abs=1e-5), socket_name


def test_roundtrip_reflective_xml(mi_addon, fresh_scene, exporter,
                                  tmp_path):
    """Reflective materials pass through XML unchanged: the registry
    importers unwrap twosided and use identity roughness mappings."""
    node = principled_node()
    node.inputs['Base Color'].default_value = (0.6, 0.3, 0.1, 1.0)
    node.inputs['Roughness'].default_value = 0.3
    node.inputs['Metallic'].default_value = 0.6
    node.inputs['Coat Weight'].default_value = 0.5
    node.inputs['Coat Roughness'].default_value = 0.1

    converter = exporter(tmp_path)
    converter.dict_to_xml(str(tmp_path / 'scene.xml'))
    bpy.ops.wm.read_homefile()
    assert bpy.ops.import_scene.mitsuba(
        filepath=str(tmp_path / 'scene.xml')) == {'FINISHED'}

    node = surface_node(bpy.data.materials['mat-Material'])
    assert node.bl_idname == 'ShaderNodeBsdfPrincipled'
    assert tuple(node.inputs['Base Color'].default_value) == \
        pytest.approx((0.6, 0.3, 0.1, 1.0))
    assert node.inputs['Roughness'].default_value == pytest.approx(0.3)
    assert node.inputs['Metallic'].default_value == pytest.approx(0.6)
    assert node.inputs['Coat Weight'].default_value == pytest.approx(0.5)
    assert node.inputs['Coat Roughness'].default_value == \
        pytest.approx(0.1)


def test_roundtrip_emission(mi_addon, fresh_scene, exporter, tmp_path):
    node = principled_node()
    node.inputs['Emission Strength'].default_value = 3.0
    node.inputs['Emission Color'].default_value = (1.0, 0.5, 0.25, 1.0)

    converter = exporter(tmp_path)
    converter.dict_to_xml(str(tmp_path / 'scene.xml'))
    bpy.ops.wm.read_homefile()
    assert bpy.ops.import_scene.mitsuba(
        filepath=str(tmp_path / 'scene.xml')) == {'FINISHED'}

    b_mat = bpy.data.materials['mat-Material']
    emission = [n for n in b_mat.node_tree.nodes
                if n.bl_idname == 'ShaderNodeEmission']
    assert len(emission) == 1
    assert emission[0].inputs['Strength'].default_value == pytest.approx(3.0)
    assert tuple(emission[0].inputs['Color'].default_value) == \
        pytest.approx((1.0, 0.5, 0.25, 1.0))
    principled = [n for n in b_mat.node_tree.nodes
                  if n.bl_idname == 'ShaderNodeBsdfPrincipled']
    assert len(principled) == 1


def test_exported_scene_dict_loads(mi_addon, fresh_scene, exporter,
                                   tmp_path):
    """A full scene with a masked, transmissive and emissive Principled
    material must load in Mitsuba."""
    import mitsuba as mi

    node = principled_node()
    node.inputs['Transmission Weight'].default_value = 0.5
    node.inputs['IOR'].default_value = 1.45
    node.inputs['Alpha'].default_value = 0.7
    node.inputs['Emission Strength'].default_value = 1.5

    converter = exporter(tmp_path, render=True)
    assert converter.dict_to_scene() is not None
