"""Refractive materials on objects that only camera rays see, or that
shadow rays ignore: the shape becomes camera-only, and a smooth principled
glass becomes a dielectric so that the camera ray keeps its class."""

import sys

import bpy
import pytest


@pytest.fixture
def exporter(mi_addon):
    import mitsuba as mi

    def _export(directory):
        mi.set_variant('scalar_rgb')
        bpy.context.scene.render.engine = 'MITSUBA'
        converter = sys.modules[mi_addon].io.exporter.SceneConverter(
            render=False)
        converter.export_ctx.directory = str(directory)
        converter.scene_to_dict(bpy.context.evaluated_depsgraph_get())
        return converter

    return _export


def camera_only(b_object):
    b_object.visible_camera = True
    for flag in ('visible_diffuse', 'visible_glossy', 'visible_transmission',
                 'visible_shadow'):
        setattr(b_object, flag, False)


def make_glass_material(name, ior=1.5, roughness=0.0):
    b_mat = bpy.data.materials.new(name)
    b_mat.use_nodes = True
    tree = b_mat.node_tree
    tree.nodes.remove(tree.nodes['Principled BSDF'])
    node = tree.nodes.new('ShaderNodeBsdfGlass')
    node.inputs['IOR'].default_value = ior
    node.inputs['Roughness'].default_value = roughness
    tree.links.new(node.outputs['BSDF'],
                   tree.nodes['Material Output'].inputs['Surface'])
    return b_mat


def make_principled_glass(name, ior=1.5, transmission=1.0,
                          color=(0.9, 0.8, 0.7, 1.0), roughness=0.0):
    b_mat = bpy.data.materials.new(name)
    b_mat.use_nodes = True
    node = b_mat.node_tree.nodes['Principled BSDF']
    node.inputs['IOR'].default_value = ior
    node.inputs['Transmission Weight'].default_value = transmission
    node.inputs['Base Color'].default_value = color
    node.inputs['Roughness'].default_value = roughness
    return b_mat


def assign(b_mat, b_object):
    b_object.data.materials.clear()
    b_object.data.materials.append(b_mat)


def as_rgb(value):
    """A spectrum parameter as a list of three floats."""
    if isinstance(value, dict):
        value = value['color'] if value['type'] == 'srgb' else value['value']
    if isinstance(value, (int, float)):
        return [float(value)] * 3
    return list(value)


def shapes_of(converter):
    return [v for v in converter.export_ctx.scene_data.values()
            if isinstance(v, dict) and v.get('type') == 'packed']


def test_principled_glass_becomes_dielectric(fresh_scene, exporter, tmp_path):
    cube = bpy.data.objects['Cube']
    assign(make_principled_glass('PGlass', ior=1.5), cube)
    camera_only(cube)
    converter = exporter(tmp_path)
    ctx = converter.export_ctx
    shape, = shapes_of(converter)
    assert shape['visibility'] == 'primary'
    assert shape['bsdf'] == ctx.create_ref('mat-PGlass-primary')
    bsdf = ctx.data_get('mat-PGlass-primary')
    while bsdf['type'] != 'dielectric':
        bsdf = bsdf['bsdf']
    assert bsdf['int_ior'] == pytest.approx(1.5)
    assert bsdf['ext_ior'] == pytest.approx(1.0)
    assert bsdf['eta_scale'] is False
    # The principled transmission tints by sqrt(base color) per interface
    assert as_rgb(bsdf['specular_transmittance']) == \
        pytest.approx([c ** 0.5 for c in (0.9, 0.8, 0.7)], rel=1e-5)
    # The original material is untouched
    original = ctx.data_get('mat-PGlass')
    while original['type'] != 'principled':
        original = original['bsdf']
    assert converter.dict_to_scene() is not None


@pytest.mark.parametrize('make', [
    lambda: make_glass_material('Mat'),
    lambda: make_principled_glass('Mat', roughness=0.4),
    lambda: make_principled_glass('Mat', transmission=0.5),
    lambda: bpy.data.materials['Material'],
], ids=['dielectric', 'rough', 'partial', 'opaque'])
def test_camera_only_object_keeps_other_materials(fresh_scene, exporter,
                                                  tmp_path, make):
    """A dielectric already keeps the camera class, a rough or partial
    refraction cannot become one, and an opaque material needs none."""
    cube = bpy.data.objects['Cube']
    b_mat = make()
    assign(b_mat, cube)
    camera_only(cube)
    converter = exporter(tmp_path)
    ctx = converter.export_ctx
    shape, = shapes_of(converter)
    assert shape['visibility'] == 'primary'
    assert shape['bsdf'] == ctx.create_ref(f'mat-{b_mat.name}')
    assert not any(k.endswith('-primary') for k in ctx.scene_data)
    assert converter.dict_to_scene() is not None


def test_shared_material_keeps_both_variants(fresh_scene, exporter, tmp_path):
    cube = bpy.data.objects['Cube']
    b_mat = make_principled_glass('Shared')
    assign(b_mat, cube)
    camera_only(cube)
    other = bpy.data.objects.new('Other', bpy.data.meshes.new_from_object(cube))
    other.location = (4.0, 0.0, 0.0)
    bpy.context.collection.objects.link(other)
    assign(b_mat, other)
    converter = exporter(tmp_path)
    refs = sorted(s['bsdf']['id'] for s in shapes_of(converter))
    assert refs == ['mat-Shared', 'mat-Shared-primary']


@pytest.mark.parametrize('refracts', [True, False])
def test_shadowless_object(fresh_scene, exporter, tmp_path, refracts):
    """A pane that bounce rays see but shadow rays ignore is exported like
    camera-only glass, which takes precedence over the shadowless wrapper
    that an opaque object without a shadow gets (test_shadowless.py)."""
    cube = bpy.data.objects['Cube']
    if refracts:
        assign(make_glass_material('Pane', ior=1.5), cube)
    cube.visible_shadow = False
    converter = exporter(tmp_path)
    ctx = converter.export_ctx
    shape, = shapes_of(converter)
    if refracts:
        assert shape['visibility'] == 'primary'
        assert shape['bsdf'] == ctx.create_ref('mat-Pane')
        assert not any(k.endswith('-shadowless') for k in ctx.scene_data)
    else:
        assert 'visibility' not in shape
        assert shape['bsdf'] == ctx.create_ref('mat-Material-shadowless')
