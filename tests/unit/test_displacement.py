"""Materials whose Material Output displaces the surface (Displacement node,
method Displacement Only or Displacement and Bump) export their meshes
wrapped in the displace shape."""

import sys

import bpy
import numpy as np
import pytest


@pytest.fixture
def exporter(mi_addon):
    import mitsuba as mi

    def _export(directory):
        mi.set_variant('scalar_rgb')
        bpy.context.scene.render.engine = 'MITSUBA'
        # The default AgX view transform would add a warning
        bpy.context.scene.view_settings.view_transform = 'Standard'
        converter = sys.modules[mi_addon].io.exporter.SceneConverter(
            render=False)
        converter.export_ctx.directory = str(directory)
        converter.scene_to_dict(bpy.context.evaluated_depsgraph_get())
        # Close the mesh container so that the entries can be loaded
        converter.export_ctx.finalize_packed()
        return converter

    return _export


def step_image():
    """A 2 x 1 Non-Color image: 0.2 on the left, 0.8 on the right."""
    image = bpy.data.images.new('step', 2, 1, alpha=False, float_buffer=True)
    image.colorspace_settings.name = 'Non-Color'
    image.pixels.foreach_set(
        np.array([0.2, 0.2, 0.2, 1.0, 0.8, 0.8, 0.8, 1.0], np.float32))
    return image


def displacing_material(name, scale=0.5, midlevel=0.0, method='DISPLACEMENT',
                        space='OBJECT', image=None):
    b_mat = bpy.data.materials.new(name)
    b_mat.use_nodes = True
    b_mat.displacement_method = method
    tree = b_mat.node_tree
    disp = tree.nodes.new('ShaderNodeDisplacement')
    disp.space = space
    disp.inputs['Scale'].default_value = scale
    disp.inputs['Midlevel'].default_value = midlevel
    if image is None:
        disp.inputs['Height'].default_value = 1.0
    else:
        tex = tree.nodes.new('ShaderNodeTexImage')
        tex.image = image
        tex.interpolation = 'Closest'
        tex.extension = 'EXTEND'
        tree.links.new(tex.outputs['Color'], disp.inputs['Height'])
    tree.links.new(disp.outputs['Displacement'],
                   tree.nodes['Material Output'].inputs['Displacement'])
    return b_mat


def plane_with(b_mat):
    bpy.ops.mesh.primitive_plane_add(size=2)
    plane = bpy.context.object
    plane.data.materials.append(b_mat)
    return plane


def shapes_of(converter):
    return [v for v in converter.export_ctx.scene_data.values()
            if isinstance(v, dict) and v.get('type') in ('packed', 'displace')]


def load_shape(entry, directory):
    """Load an exported shape entry on its own, with a plain material."""
    import mitsuba as mi
    from bl_ext.user_default.mitsuba_blender.convert.export.materials \
        ._resolve import _absolutify_filenames
    entry = _absolutify_filenames(entry, str(directory))
    entry['bsdf'] = {'type': 'diffuse'}
    return mi.load_dict(entry)


def test_constant_height(fresh_scene, exporter, tmp_path):
    plane = plane_with(displacing_material('Disp', scale=0.05, midlevel=0.25))
    converter = exporter(tmp_path)
    shapes = shapes_of(converter)
    assert len(shapes) == 2 # the default cube and the plane
    entry = next(s for s in shapes if s['type'] == 'displace')
    assert entry['mesh']['type'] == 'packed'
    assert 'to_world' not in entry['mesh'] and 'to_world' in entry
    assert entry['height'] == 1.0
    assert entry['scale'] == pytest.approx(0.05)
    assert entry['midlevel'] == pytest.approx(0.25)
    assert converter.export_ctx.warnings == []

    mesh = load_shape(entry, tmp_path)
    p = np.array(mesh.positions())
    assert np.allclose(p[:, 2], (1.0 - 0.25) * 0.05)
    # The plane is flat shaded, like its displaced version in Cycles
    assert entry['face_normals'] and mesh.has_face_normals()


def test_smooth_shading_keeps_vertex_normals(fresh_scene, exporter, tmp_path):
    plane = plane_with(displacing_material('Disp', scale=0.05))
    plane.data.shade_smooth()
    converter = exporter(tmp_path)
    entry = next(s for s in shapes_of(converter) if s['type'] == 'displace')
    assert 'face_normals' not in entry
    assert not load_shape(entry, tmp_path).has_face_normals()


def test_height_texture(fresh_scene, exporter, tmp_path):
    plane_with(displacing_material('Disp', scale=0.05, image=step_image(),
                                   method='BOTH'))
    converter = exporter(tmp_path)
    entry = next(s for s in shapes_of(converter) if s['type'] == 'displace')
    assert entry['height']['type'] == 'bitmap'
    assert entry['height']['raw'] is True

    mesh = load_shape(entry, tmp_path)
    p = np.array(mesh.positions())
    # The image is written with 8 bits per channel
    assert np.allclose(p[p[:, 0] < 0, 2], 0.2 * 0.05, atol=1e-4)
    assert np.allclose(p[p[:, 0] > 0, 2], 0.8 * 0.05, atol=1e-4)
    assert converter.export_ctx.warnings == []


def test_bump_method_is_not_displaced(fresh_scene, exporter, tmp_path):
    plane_with(displacing_material('Disp', method='BUMP'))
    converter = exporter(tmp_path)
    assert all(s['type'] == 'packed' for s in shapes_of(converter))
    assert converter.export_ctx.warnings == []


def test_world_space_uses_object_scale(fresh_scene, exporter, tmp_path):
    plane = plane_with(displacing_material('Disp', scale=0.05, space='WORLD'))
    plane.scale = (2.0, 2.0, 2.0)
    converter = exporter(tmp_path)
    entry = next(s for s in shapes_of(converter) if s['type'] == 'displace')
    assert entry['scale'] == pytest.approx(0.025)
    assert converter.export_ctx.warnings == []

    # The world-space offset is the node's scale
    mesh = load_shape(entry, tmp_path)
    p = np.array(mesh.positions())
    assert np.allclose(p[:, 2], 0.05)
    assert np.allclose(np.abs(p[:, 0]), 2.0)


def test_unsupported_displacement_warns(fresh_scene, exporter, tmp_path):
    b_mat = bpy.data.materials.new('Vector')
    b_mat.use_nodes = True
    b_mat.displacement_method = 'DISPLACEMENT'
    tree = b_mat.node_tree
    disp = tree.nodes.new('ShaderNodeVectorDisplacement')
    tree.links.new(disp.outputs['Displacement'],
                   tree.nodes['Material Output'].inputs['Displacement'])
    plane_with(b_mat)
    converter = exporter(tmp_path)
    assert all(s['type'] == 'packed' for s in shapes_of(converter))
    assert any('VECTOR_DISPLACEMENT' in w for w in converter.export_ctx.warnings)


def test_subdivision_modifier_is_honoured(fresh_scene, exporter, tmp_path):
    plane = plane_with(displacing_material('Disp', scale=0.05,
                                           image=step_image()))
    mod = plane.modifiers.new('Subdivision', 'SUBSURF')
    mod.subdivision_type = 'SIMPLE'
    mod.levels = 2
    converter = exporter(tmp_path)
    entry = next(s for s in shapes_of(converter) if s['type'] == 'displace')
    mesh = load_shape(entry, tmp_path)
    assert mesh.face_count() == 32
    assert converter.export_ctx.warnings == []


def test_multi_material_object(fresh_scene, exporter, tmp_path):
    bpy.ops.mesh.primitive_plane_add(size=2)
    plane = bpy.context.object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.subdivide(number_cuts=1)
    bpy.ops.object.mode_set(mode='OBJECT')
    plane.data.materials.append(displacing_material('Disp', scale=0.05))
    plane.data.materials.append(bpy.data.materials.new('Flat'))
    for i, poly in enumerate(plane.data.polygons):
        poly.material_index = int(poly.center.x > 0)
    converter = exporter(tmp_path)
    types = sorted(s['type'] for s in shapes_of(converter))
    assert types == ['displace', 'packed', 'packed']
    entry = next(s for s in shapes_of(converter) if s['type'] == 'displace')
    p = np.array(load_shape(entry, tmp_path).positions())
    assert np.all(p[:, 0] <= 1e-6) and np.allclose(p[:, 2], 0.05)


def test_missing_uvs_and_large_amplitude(fresh_scene, exporter, tmp_path):
    plane = plane_with(displacing_material('Disp', scale=0.05,
                                           image=step_image()))
    plane.data.uv_layers.remove(plane.data.uv_layers[0])
    converter = exporter(tmp_path)
    assert all(s['type'] == 'packed' for s in shapes_of(converter))
    assert any('no UV map' in w for w in converter.export_ctx.warnings)

    bpy.data.objects.remove(plane)
    plane = plane_with(displacing_material('Large', scale=0.5))
    converter = exporter(tmp_path)
    assert any('unusually large' in w for w in converter.export_ctx.warnings)


def test_adaptive_subdivision_warns(fresh_scene, exporter, tmp_path):
    plane = plane_with(displacing_material('Disp', scale=0.05))
    mod = plane.modifiers.new('Subdivision', 'SUBSURF')
    mod.use_adaptive_subdivision = True
    converter = exporter(tmp_path)
    assert any(s['type'] == 'displace' for s in shapes_of(converter))
    assert any('adaptive subdivision' in w
               for w in converter.export_ctx.warnings)
