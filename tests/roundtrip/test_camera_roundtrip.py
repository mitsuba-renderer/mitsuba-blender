"""Numeric round trips of camera parameters through export and import."""

import bpy
import pytest
from mathutils import Euler, Matrix


def _roundtrip(tmp_path):
    scene_file = tmp_path / 'scene.xml'
    bpy.context.scene.render.engine = 'MITSUBA'
    assert bpy.ops.export_scene.mitsuba(filepath=str(scene_file)) == \
        {'FINISHED'}
    assert bpy.ops.import_scene.mitsuba(filepath=str(scene_file)) == \
        {'FINISHED'}
    camera = bpy.context.scene.camera
    assert camera is not None
    return camera


def _pose_camera():
    camera = bpy.data.objects['Camera']
    camera.matrix_world = Matrix.Translation((1.0, -2.0, 3.0)) @ \
        Euler((1.1, 0.2, 0.7)).to_matrix().to_4x4()
    bpy.context.view_layer.update()
    return camera


def _assert_same_pose(matrix_a, matrix_b, tol=1e-4):
    delta = [abs(a - b) for row_a, row_b in zip(matrix_a, matrix_b)
             for a, b in zip(row_a, row_b)]
    assert max(delta) < tol


def test_perspective_roundtrip(mi_addon, fresh_scene, tmp_path):
    scene = bpy.context.scene
    scene.render.resolution_x = 640
    scene.render.resolution_y = 480
    camera = _pose_camera()
    camera.data.lens = 35.0
    camera.data.shift_x = 0.15
    camera.data.shift_y = -0.05
    camera.data.clip_start = 0.5
    camera.data.clip_end = 500.0
    original_matrix = camera.matrix_world.copy()
    original_angle = camera.data.angle_x

    imported = _roundtrip(tmp_path)

    assert imported.data.type == 'PERSP'
    assert imported.data.angle_x == pytest.approx(original_angle, rel=1e-5)
    assert imported.data.shift_x == pytest.approx(0.15, rel=1e-5)
    assert imported.data.shift_y == pytest.approx(-0.05, rel=1e-5)
    assert imported.data.clip_start == pytest.approx(0.5)
    assert imported.data.clip_end == pytest.approx(500.0)
    _assert_same_pose(imported.matrix_world, original_matrix)


def test_portrait_fov_roundtrip(mi_addon, fresh_scene, tmp_path):
    scene = bpy.context.scene
    scene.render.resolution_x = 480
    scene.render.resolution_y = 640
    camera = bpy.data.objects['Camera']
    camera.data.lens = 42.0
    original_angle = camera.data.angle_x

    imported = _roundtrip(tmp_path)
    assert imported.data.angle_x == pytest.approx(original_angle, rel=1e-5)


def test_dof_roundtrip(mi_addon, fresh_scene, tmp_path):
    camera = bpy.data.objects['Camera']
    camera.data.lens = 80.0
    camera.data.dof.use_dof = True
    camera.data.dof.aperture_fstop = 2.8
    camera.data.dof.focus_distance = 4.2
    original_angle = camera.data.angle_x

    imported = _roundtrip(tmp_path)

    assert imported.data.dof.use_dof
    assert imported.data.angle_x == pytest.approx(original_angle, rel=1e-5)
    assert imported.data.dof.aperture_fstop == pytest.approx(2.8, rel=1e-5)
    assert imported.data.dof.focus_distance == pytest.approx(4.2, rel=1e-5)


def test_orthographic_roundtrip(mi_addon, fresh_scene, tmp_path):
    scene = bpy.context.scene
    scene.render.resolution_x = 640
    scene.render.resolution_y = 480
    camera = _pose_camera()
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = 5.0
    original_matrix = camera.matrix_world.copy()

    imported = _roundtrip(tmp_path)

    assert imported.data.type == 'ORTHO'
    assert imported.data.ortho_scale == pytest.approx(5.0, rel=1e-5)
    _assert_same_pose(imported.matrix_world, original_matrix)
