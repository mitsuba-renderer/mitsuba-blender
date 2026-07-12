"""Export-side geometry tests: Blender meshes -> mi.Mesh."""

import os
import sys

import bpy
import numpy as np
import pytest


@pytest.fixture
def exporter(mi_addon):
    """Returns a function that exports the current scene to a Mitsuba scene."""
    import mitsuba as mi

    def _export(directory, render=True):
        mi.set_variant('scalar_rgb')
        bpy.context.scene.render.engine = 'MITSUBA'
        converter = sys.modules[mi_addon].io.exporter.SceneConverter(render=render)
        converter.export_ctx.directory = str(directory)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        converter.scene_to_dict(depsgraph)
        return converter

    return _export


def scene_meshes(mi_scene):
    import mitsuba as mi
    return [s for s in mi_scene.shapes() if isinstance(s, mi.Mesh)]


def test_render_mode_keeps_meshes_in_memory(fresh_scene, exporter, tmp_path):
    converter = exporter(tmp_path, render=True)
    scene = converter.dict_to_scene()

    # No mesh files may be written in render mode
    assert not os.path.isdir(os.path.join(str(tmp_path), 'meshes'))

    meshes = scene_meshes(scene)
    assert len(meshes) == 1
    mesh = meshes[0]
    assert mesh.face_count() == 12
    assert mesh.has_vertex_normals()
    assert mesh.has_vertex_texcoords()
    # The flat-shaded cube welds corners that share normals and UVs
    assert 8 < mesh.vertex_count() <= 36
    bbox = mesh.bbox()
    assert np.allclose(list(bbox.min), [-1, -1, -1], atol=1e-5)
    assert np.allclose(list(bbox.max), [1, 1, 1], atol=1e-5)


def test_file_export_writes_ply(fresh_scene, exporter, tmp_path):
    bpy.data.objects['Cube'].location = (2.0, 0.0, 0.0)
    converter = exporter(tmp_path, render=False)
    converter.dict_to_xml(str(tmp_path / 'scene.xml'))

    ply_files = os.listdir(tmp_path / 'meshes')
    assert ply_files == ['Cube.ply']

    import mitsuba as mi
    scene = mi.load_file(str(tmp_path / 'scene.xml'))
    meshes = scene_meshes(scene)
    assert len(meshes) == 1
    # The object transform is baked into the vertex data
    center = 0.5 * (np.array(list(meshes[0].bbox().min))
                    + np.array(list(meshes[0].bbox().max)))
    assert np.allclose(center, [2, 0, 0], atol=1e-5)


def test_smooth_shading_welds_vertices(fresh_scene, exporter, tmp_path):
    bpy.ops.mesh.primitive_monkey_add()
    bpy.ops.object.shade_smooth()
    b_mesh = bpy.context.active_object.data
    b_mesh.calc_loop_triangles()
    tri_count = len(b_mesh.loop_triangles)
    vert_count = len(b_mesh.vertices)

    converter = exporter(tmp_path, render=True)
    scene = converter.dict_to_scene()
    suzanne = [m for m in scene_meshes(scene) if m.face_count() == tri_count]
    assert len(suzanne) == 1
    # Smooth shading shares normals, so welding gets close to the original
    # vertex count instead of one vertex per corner
    assert suzanne[0].vertex_count() < 1.2 * vert_count


def test_mirrored_object_keeps_orientation(fresh_scene, exporter, tmp_path):
    bpy.data.objects['Cube'].scale = (-1.0, 1.0, 1.0)
    converter = exporter(tmp_path, render=True)
    scene = converter.dict_to_scene()
    mesh = scene_meshes(scene)[0]
    params = __import__('mitsuba').traverse(mesh)
    positions = np.array(params['vertex_positions']).reshape(-1, 3)
    normals = np.array(params['vertex_normals']).reshape(-1, 3)
    # Normals still point away from the center after mirroring
    assert np.all(np.sum(positions * normals, axis=1) > 0)


def test_multi_material_split(fresh_scene, exporter, tmp_path):
    b_obj = bpy.data.objects['Cube']
    second = bpy.data.materials.new('Second')
    b_obj.data.materials.append(second)
    for face in b_obj.data.polygons[:2]:
        face.material_index = 1

    converter = exporter(tmp_path, render=False)
    plys = [v for v in converter.export_ctx.scene_data.values()
            if isinstance(v, dict) and v.get('type') == 'ply']
    assert len(plys) == 2
    assert plys[0]['bsdf']['id'] != plys[1]['bsdf']['id']

    scene = converter.dict_to_scene()
    face_counts = sorted(m.face_count() for m in scene_meshes(scene))
    assert face_counts == [4, 8]


def test_emissive_material_render_mode(fresh_scene, exporter, tmp_path):
    b_mat = bpy.data.materials.new('Emitter')
    b_mat.use_nodes = True
    tree = b_mat.node_tree
    tree.nodes.remove(tree.nodes['Principled BSDF'])
    emission = tree.nodes.new('ShaderNodeEmission')
    emission.inputs['Strength'].default_value = 5.0
    tree.links.new(emission.outputs['Emission'],
                   tree.nodes['Material Output'].inputs['Surface'])
    bpy.data.objects['Cube'].data.materials.clear()
    bpy.data.objects['Cube'].data.materials.append(b_mat)

    converter = exporter(tmp_path, render=True)
    scene = converter.dict_to_scene()
    mesh = scene_meshes(scene)[0]
    assert mesh.emitter() is not None


def test_vertex_colors_roundtrip(fresh_scene, exporter, tmp_path):
    b_mesh = bpy.data.objects['Cube'].data
    attr = b_mesh.color_attributes.new('Col', 'FLOAT_COLOR', 'POINT')
    color = np.tile([0.25, 0.5, 0.75, 1.0], len(b_mesh.vertices))
    attr.data.foreach_set('color', color)

    converter = exporter(tmp_path, render=False)
    converter.dict_to_xml(str(tmp_path / 'scene.xml'))

    import mitsuba as mi
    mesh = mi.load_dict({
        'type': 'ply',
        'filename': str(tmp_path / 'meshes' / 'Cube.ply'),
    })
    params = mi.traverse(mesh)
    values = np.array(params['vertex_Col']).reshape(-1, 3)
    assert np.allclose(values, [0.25, 0.5, 0.75], atol=1e-5)


def test_faceless_mesh_does_not_abort_export(fresh_scene, exporter, tmp_path):
    b_mesh = bpy.data.meshes.new('Wire')
    b_mesh.from_pydata([(0, 0, 0), (1, 0, 0)], [(0, 1)], [])
    b_mesh.materials.append(bpy.data.materials.new('WireMat'))
    b_obj = bpy.data.objects.new('Wire', b_mesh)
    bpy.context.scene.collection.objects.link(b_obj)

    converter = exporter(tmp_path, render=True)
    scene = converter.dict_to_scene()
    # Only the default cube survives; the faceless mesh is skipped
    assert len(scene_meshes(scene)) == 1
    assert any('no faces' in w for w in converter.export_ctx.warnings)


def test_empty_material_slot_uses_default_bsdf(fresh_scene, exporter,
                                               tmp_path):
    b_obj = bpy.data.objects['Cube']
    b_obj.data.materials.clear()
    b_obj.data.materials.append(None)
    b_obj.data.materials.append(bpy.data.materials.new('Second'))
    for face in b_obj.data.polygons[:2]:
        face.material_index = 1

    converter = exporter(tmp_path, render=False)
    plys = [v for v in converter.export_ctx.scene_data.values()
            if isinstance(v, dict) and v.get('type') == 'ply']
    assert len(plys) == 2
    assert {p['bsdf']['id'] for p in plys} == {'default-bsdf', 'mat-Second'}

    scene = converter.dict_to_scene()
    assert sorted(m.face_count() for m in scene_meshes(scene)) == [4, 8]
