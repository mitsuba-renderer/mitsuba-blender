"""Import-side geometry tests: mi shapes -> Blender meshes, and roundtrips."""

import glob
import os
import sys

import bpy
import numpy as np
import pytest

SCENES_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.realpath(__file__))), 'res', 'scenes')
SCENE_FILES = sorted(glob.glob(os.path.join(SCENES_DIR, '*.xml')))


def export_scene(mi_addon, filepath):
    import mitsuba as mi
    mi.set_variant('scalar_rgb')
    bpy.context.scene.render.engine = 'MITSUBA'
    converter = sys.modules[mi_addon].io.exporter.SceneConverter(render=False)
    converter.export_ctx.directory = os.path.dirname(filepath)
    converter.scene_to_dict(bpy.context.evaluated_depsgraph_get())
    converter.dict_to_xml(filepath)


def imported_meshes():
    return [o for o in bpy.context.scene.objects if o.type == 'MESH']


@pytest.mark.parametrize('scene_file', SCENE_FILES,
                         ids=[os.path.basename(f) for f in SCENE_FILES])
def test_import_scene_files(mi_addon, fresh_scene, scene_file):
    assert bpy.ops.import_scene.mitsuba(filepath=scene_file) == {'FINISHED'}


def test_import_ply_shape(mi_addon, fresh_scene):
    scene_file = os.path.join(SCENES_DIR, 'test1.xml')
    assert bpy.ops.import_scene.mitsuba(filepath=scene_file) == {'FINISHED'}

    meshes = imported_meshes()
    assert len(meshes) == 1
    b_mesh = meshes[0].data
    b_mesh.calc_loop_triangles()
    assert len(b_mesh.loop_triangles) == 12
    assert b_mesh.materials[0] is not None
    # The scene requests face normals, which map to flat shading
    assert all(not p.use_smooth for p in b_mesh.polygons)


def test_roundtrip_smooth_suzanne(mi_addon, fresh_scene, tmp_path):
    bpy.ops.mesh.primitive_monkey_add()
    bpy.ops.object.shade_smooth()
    b_mesh = bpy.context.active_object.data
    b_mesh.calc_loop_triangles()
    tri_count = len(b_mesh.loop_triangles)
    bounds = np.array([v.co for v in b_mesh.vertices])

    scene_file = str(tmp_path / 'scene.xml')
    export_scene(mi_addon, scene_file)
    assert bpy.ops.import_scene.mitsuba(filepath=scene_file) == {'FINISHED'}

    meshes = [o for o in imported_meshes()
              if len(o.data.polygons) == tri_count]
    assert len(meshes) == 1
    imported = meshes[0].data
    assert imported.uv_layers
    assert all(p.use_smooth for p in imported.polygons)
    imported_bounds = np.array([v.co for v in imported.vertices])
    assert np.allclose(bounds.min(axis=0), imported_bounds.min(axis=0),
                       atol=1e-4)
    assert np.allclose(bounds.max(axis=0), imported_bounds.max(axis=0),
                       atol=1e-4)


def test_roundtrip_flat_cube_normals(mi_addon, fresh_scene, tmp_path):
    scene_file = str(tmp_path / 'scene.xml')
    export_scene(mi_addon, scene_file)
    assert bpy.ops.import_scene.mitsuba(filepath=scene_file) == {'FINISHED'}

    meshes = [o for o in imported_meshes() if len(o.data.polygons) == 12]
    assert len(meshes) == 1
    b_mesh = meshes[0].data
    normals = np.empty(len(b_mesh.loops) * 3, dtype=np.float32)
    b_mesh.corner_normals.foreach_get('vector', normals)
    normals = normals.reshape(-1, 3, 3)
    # The default cube is flat shaded: every triangle has a uniform normal
    assert np.allclose(normals[:, 0], normals[:, 1], atol=1e-5)
    assert np.allclose(normals[:, 0], normals[:, 2], atol=1e-5)


def test_roundtrip_multi_material(mi_addon, fresh_scene, tmp_path):
    b_obj = bpy.data.objects['Cube']
    second = bpy.data.materials.new('Second')
    b_obj.data.materials.append(second)
    for face in b_obj.data.polygons[:2]:
        face.material_index = 1

    scene_file = str(tmp_path / 'scene.xml')
    export_scene(mi_addon, scene_file)
    assert bpy.ops.import_scene.mitsuba(filepath=scene_file) == {'FINISHED'}

    meshes = imported_meshes()
    assert sorted(len(o.data.polygons) for o in meshes) == [4, 8]
    mat_names = {o.data.materials[0].name for o in meshes}
    assert len(mat_names) == 2


def test_roundtrip_vertex_colors(mi_addon, fresh_scene, tmp_path):
    b_mesh = bpy.data.objects['Cube'].data
    attr = b_mesh.color_attributes.new('Col', 'FLOAT_COLOR', 'POINT')
    color = np.tile([0.25, 0.5, 0.75, 1.0], len(b_mesh.vertices))
    attr.data.foreach_set('color', color)

    scene_file = str(tmp_path / 'scene.xml')
    export_scene(mi_addon, scene_file)
    assert bpy.ops.import_scene.mitsuba(filepath=scene_file) == {'FINISHED'}

    meshes = [o for o in imported_meshes() if len(o.data.polygons) == 12]
    imported = meshes[0].data
    assert 'Col' in imported.color_attributes
    values = np.empty(len(imported.color_attributes['Col'].data) * 4,
                      dtype=np.float32)
    imported.color_attributes['Col'].data.foreach_get('color', values)
    assert np.allclose(values.reshape(-1, 4)[:, :3], [0.25, 0.5, 0.75],
                       atol=1e-5)
