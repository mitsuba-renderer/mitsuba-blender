"""Export-side geometry tests: Blender meshes -> mi.Mesh."""

import os
import re
import sys

import bpy
import numpy as np
import pytest


@pytest.fixture
def exporter(mi_addon):
    """Returns a function that exports the current scene to a Mitsuba scene."""
    import mitsuba as mi

    def _export(directory, render=True, blender_triangulation=False):
        mi.set_variant('scalar_rgb')
        bpy.context.scene.render.engine = 'MITSUBA'
        converter = sys.modules[mi_addon].io.exporter.SceneConverter(render=render)
        converter.export_ctx.directory = str(directory)
        converter.export_ctx.blender_triangulation = blender_triangulation
        depsgraph = bpy.context.evaluated_depsgraph_get()
        converter.scene_to_dict(depsgraph)
        return converter

    return _export


def scene_meshes(mi_scene):
    import mitsuba as mi
    return [s for s in mi_scene.shapes() if isinstance(s, mi.Mesh)]


def triangle_loops(b_mesh, triangulate):
    """The loop indices of each triangle corner, triangulated the way the
    exporter asked for: Blender's own split, or the fan around each
    polygon's first corner that Mitsuba applies."""
    if triangulate == 'blender':
        b_mesh.calc_loop_triangles()
        loops = np.empty(len(b_mesh.loop_triangles) * 3, dtype=np.int32)
        b_mesh.loop_triangles.foreach_get('loops', loops)
        return loops.reshape(-1, 3)

    starts = np.empty(len(b_mesh.polygons), dtype=np.int32)
    b_mesh.polygons.foreach_get('loop_start', starts)
    totals = np.empty(len(b_mesh.polygons), dtype=np.int32)
    b_mesh.polygons.foreach_get('loop_total', totals)
    return np.array([[s, s + i, s + i + 1]
                     for s, n in zip(starts, totals)
                     for i in range(1, n - 1)], dtype=np.int32)


def blender_corners(b_obj, axis_mat, triangulate):
    """Blender's own per-triangle-corner data, in Mitsuba world space.

    This mirrors the exporter's conventions (axis conversion, baked object
    transform, flipped V coordinate, reversed winding under a mirroring
    transform) without sharing any of its code, so that the exported mesh
    can be compared against it corner by corner.
    """
    b_mesh = b_obj.data
    n_loops = len(b_mesh.loops)

    tri_loops = triangle_loops(b_mesh, triangulate)
    loop_vert = np.empty(n_loops, dtype=np.int32)
    b_mesh.loops.foreach_get('vertex_index', loop_vert)
    co = np.empty(len(b_mesh.vertices) * 3, dtype=np.float32)
    b_mesh.vertices.foreach_get('co', co)
    normals = np.empty(n_loops * 3, dtype=np.float32)
    b_mesh.corner_normals.foreach_get('vector', normals)

    uvs = None
    for layer in b_mesh.uv_layers:
        if layer.active_render:
            uvs = np.empty(n_loops * 2, dtype=np.float32)
            layer.uv.foreach_get('vector', uvs)
            uvs = uvs.reshape(-1, 2).astype(np.float64)
            break

    colors = {}
    for attr in b_mesh.color_attributes:
        values = np.empty(len(attr.data) * 4, dtype=np.float32)
        attr.data.foreach_get('color', values)
        values = values.reshape(-1, 4)[:, :3].astype(np.float64)
        # Attribute names reach Mitsuba with their non-word characters
        # replaced, see sanitize_attribute_name()
        colors[re.sub(r'\W', '_', attr.name)] = \
            values[loop_vert] if attr.domain == 'POINT' else values

    to_world = np.array(axis_mat @ b_obj.matrix_world, dtype=np.float64)
    rot = to_world[:3, :3]
    corners = tri_loops
    if np.linalg.det(rot) < 0:
        corners = corners[:, ::-1]
    corners = corners.ravel()

    positions = co.reshape(-1, 3).astype(np.float64) @ rot.T + to_world[:3, 3]
    n = normals.reshape(-1, 3).astype(np.float64) @ np.linalg.inv(rot)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-20)

    out = {'positions': positions[loop_vert[corners]], 'normals': n[corners]}
    if uvs is not None:
        out['texcoords'] = uvs[corners]
    for name, values in colors.items():
        out[name] = values[corners]
    return out


def mitsuba_corners(mesh, color_names=()):
    """The same per-corner data, read back from the exported mi.Mesh."""
    faces = np.array(mesh.faces()).reshape(-1, 3).ravel()
    attrs = {name: np.array(mesh.attribute(f'vertex_{name}')).reshape(-1, 3)
             for name in color_names}

    out = {'positions': np.array([list(mesh.vertex_position(int(v)))
                                  for v in faces]),
           'normals': np.array([list(mesh.vertex_normal(int(v)))
                                for v in faces])}
    if mesh.has_texcoords():
        out['texcoords'] = np.array([list(mesh.vertex_texcoord(int(v)))
                                     for v in faces])
    for name, values in attrs.items():
        out[name] = values[faces]
    return out


def sole_mesh_object(build):
    """Clears the scene's mesh objects, then runs `build` to add one."""
    for obj in [o for o in bpy.data.objects if o.type == 'MESH']:
        bpy.data.objects.remove(obj, do_unlink=True)
    build()
    return bpy.context.active_object


def add_ngon_grid():
    b_mesh = bpy.data.meshes.new('Ngons')
    verts = [(x, y, 0.1 * x * y) for y in range(3) for x in range(4)]
    # A pentagon, a quad and a triangle, so the fan triangulation and the
    # per-polygon corner counts both vary
    faces = [(0, 1, 5, 6, 4), (1, 2, 6, 5), (2, 3, 7)]
    b_mesh.from_pydata(verts, [], faces)
    b_mesh.update()
    uv = b_mesh.uv_layers.new(name='UVMap')
    for i in range(len(b_mesh.loops)):
        uv.uv[i].vector = (0.1 * i, 0.05 * i)
    obj = bpy.data.objects.new('Ngons', b_mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj


def add_colored_cube():
    bpy.ops.mesh.primitive_cube_add()
    b_mesh = bpy.context.active_object.data
    per_corner = b_mesh.color_attributes.new('Corner Col', 'FLOAT_COLOR',
                                             'CORNER')
    rng = np.random.RandomState(3)
    per_corner.data.foreach_set(
        'color', rng.rand(len(per_corner.data) * 4).astype(np.float32))
    per_point = b_mesh.color_attributes.new('PtCol', 'FLOAT_COLOR', 'POINT')
    per_point.data.foreach_set(
        'color', rng.rand(len(per_point.data) * 4).astype(np.float32))


MESH_CASES = {
    'flat_cube': (lambda: bpy.ops.mesh.primitive_cube_add(), None, ()),
    'smooth_sphere': (lambda: (bpy.ops.mesh.primitive_uv_sphere_add(),
                               bpy.ops.object.shade_smooth()), None, ()),
    'suzanne': (lambda: bpy.ops.mesh.primitive_monkey_add(), None, ()),
    'mirrored': (lambda: bpy.ops.mesh.primitive_cylinder_add(),
                 (-1.0, 1.0, 2.0), ()),
    'ngons': (add_ngon_grid, None, ()),
    'colors': (add_colored_cube, (0.5, -1.5, 1.0), ('Corner_Col', 'PtCol')),
}


@pytest.mark.parametrize('case', sorted(MESH_CASES))
@pytest.mark.parametrize('triangulate', ['mitsuba', 'blender'])
def test_corner_data_matches_blender(fresh_scene, exporter, tmp_path, case,
                                     triangulate):
    """Every triangle corner of the exported mesh carries the values that
    Blender holds for the loop it came from. This covers the corner-indexed
    Mesh construction end to end: welding, vertex splitting at normal and
    UV seams, the fan triangulation of n-gons, and the winding flip and
    inverse-transpose normals of a mirroring transform."""
    build, scale, color_names = MESH_CASES[case]
    b_obj = sole_mesh_object(build)
    if scale is not None:
        b_obj.scale = scale

    converter = exporter(tmp_path, render=True,
                         blender_triangulation=triangulate == 'blender')
    scene = converter.dict_to_scene()
    meshes = scene_meshes(scene)
    assert len(meshes) == 1
    mesh = meshes[0]

    depsgraph = bpy.context.evaluated_depsgraph_get()
    reference = blender_corners(b_obj.evaluated_get(depsgraph),
                                converter.export_ctx.axis_mat, triangulate)
    assert mesh.face_count() == len(reference['positions']) // 3

    exported = mitsuba_corners(mesh, color_names)
    assert sorted(exported) == sorted(reference)
    for key, expected in reference.items():
        assert np.allclose(exported[key], expected, atol=1e-5), \
            f'{case}: {key} differs'

    # Welding must not leave one vertex per corner behind
    assert mesh.vertex_count() < len(reference['positions'])


def test_render_mode_keeps_meshes_in_memory(fresh_scene, exporter, tmp_path):
    converter = exporter(tmp_path, render=True)
    scene = converter.dict_to_scene()

    # No mesh files may be written in render mode
    assert not os.path.isdir(os.path.join(str(tmp_path), 'meshes'))

    meshes = scene_meshes(scene)
    assert len(meshes) == 1
    mesh = meshes[0]
    assert mesh.face_count() == 12
    assert mesh.has_normals()
    assert mesh.has_texcoords()
    # The flat-shaded cube welds corners that share normals and UVs
    assert 8 < mesh.vertex_count() <= 36
    bbox = mesh.bbox()
    assert np.allclose(list(bbox.min), [-1, -1, -1], atol=1e-5)
    assert np.allclose(list(bbox.max), [1, 1, 1], atol=1e-5)


def test_file_export_writes_serialized(fresh_scene, exporter, tmp_path):
    bpy.data.objects['Cube'].location = (2.0, 0.0, 0.0)
    converter = exporter(tmp_path, render=False)
    converter.dict_to_xml(str(tmp_path / 'scene.xml'))

    # Every mesh lives in one shared file, referenced by sub-mesh index
    assert os.listdir(tmp_path / 'meshes') == ['meshes.serialized']

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


def vertex_arrays(mesh):
    """Per-vertex positions and normals, which the mesh may store at a
    coarser granularity internally."""
    n = mesh.vertex_count()
    return (np.array([list(mesh.vertex_position(i)) for i in range(n)]),
            np.array([list(mesh.vertex_normal(i)) for i in range(n)]))


def test_mirrored_object_keeps_orientation(fresh_scene, exporter, tmp_path):
    bpy.data.objects['Cube'].scale = (-1.0, 1.0, 1.0)
    converter = exporter(tmp_path, render=True)
    scene = converter.dict_to_scene()
    mesh = scene_meshes(scene)[0]
    positions, normals = vertex_arrays(mesh)
    # Normals still point away from the center after mirroring
    assert np.all(np.sum(positions * normals, axis=1) > 0)


def distinct_material(name, color):
    """A material that differs from the default one, so that Mitsuba does
    not merge the shapes using them into a single mesh."""
    b_mat = bpy.data.materials.new(name)
    if b_mat.node_tree is None:
        # Blender releases before 5.0 start without a node tree
        b_mat.use_nodes = True
    b_mat.node_tree.nodes['Principled BSDF'] \
        .inputs['Base Color'].default_value = color
    return b_mat


def test_multi_material_split(fresh_scene, exporter, tmp_path):
    b_obj = bpy.data.objects['Cube']
    b_obj.data.materials.append(distinct_material('Second', (1, 0, 0, 1)))
    for face in b_obj.data.polygons[:2]:
        face.material_index = 1

    converter = exporter(tmp_path, render=False)
    parts = [v for v in converter.export_ctx.scene_data.values()
            if isinstance(v, dict) and v.get('type') == 'serialized']
    assert len(parts) == 2
    assert parts[0]['bsdf']['id'] != parts[1]['bsdf']['id']
    assert {p['shape_index'] for p in parts} == {0, 1}

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
        'type': 'serialized',
        'filename': str(tmp_path / 'meshes' / 'meshes.serialized'),
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
    parts = [v for v in converter.export_ctx.scene_data.values()
            if isinstance(v, dict) and v.get('type') == 'serialized']
    assert len(parts) == 2
    assert {p['bsdf']['id'] for p in parts} == {'default-bsdf', 'mat-Second'}

    scene = converter.dict_to_scene()
    assert sorted(m.face_count() for m in scene_meshes(scene)) == [4, 8]


def test_material_name_with_path_separator(fresh_scene, exporter, tmp_path):
    # Part filenames embed the material name; a separator in it must not
    # make write_ply target a nonexistent subdirectory
    b_obj = bpy.data.objects['Cube']
    b_obj.data.materials.append(
        distinct_material('metal/rough', (0, 1, 0, 1)))
    for face in b_obj.data.polygons[:2]:
        face.material_index = 1

    converter = exporter(tmp_path, render=False)
    converter.dict_to_xml(str(tmp_path / 'scene.xml'))
    assert os.listdir(tmp_path / 'meshes') == ['meshes.serialized']

    import mitsuba as mi
    scene = mi.load_file(str(tmp_path / 'scene.xml'))
    assert len(scene_meshes(scene)) == 2


def test_out_of_range_material_index_not_dropped(fresh_scene, exporter,
                                                 tmp_path):
    # Indices beyond the slot count come from slot deletion via the API or
    # imported files; Blender clamps them at render time
    b_mesh = bpy.data.objects['Cube'].data
    for face in b_mesh.polygons[:3]:
        face.material_index = 7

    converter = exporter(tmp_path, render=True)
    scene = converter.dict_to_scene()
    assert sum(m.face_count() for m in scene_meshes(scene)) == 12
