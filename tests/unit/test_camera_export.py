"""Camera export through convert.export.camera.

The numeric tests compare the exported Mitsuba sensor against Blender's own
view frame (camera.view_frame), so they verify the actual imaging geometry
rather than just the dict layout.
"""

import math

import bpy
import pytest
from mathutils import Matrix, Vector


def _export_scene_dict():
    from bl_ext.user_default.mitsuba_blender.io.exporter import SceneConverter
    bpy.context.scene.render.engine = 'MITSUBA'
    converter = SceneConverter(render=True)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    converter.scene_to_dict(depsgraph)
    return converter.export_ctx.scene_data


def _sensor_dict(scene_data):
    sensors = [v for v in scene_data.values()
               if isinstance(v, dict) and v.get('type') in
               ('perspective', 'thinlens', 'orthographic')]
    assert len(sensors) == 1
    return sensors[0]


def _camera():
    return bpy.data.objects['Camera']


def _load_sensor(sensor_dict):
    import mitsuba as mi
    mi.set_variant('scalar_rgb')
    return mi.load_dict(sensor_dict)


def _center_ray(sensor_dict):
    """World-space origin and direction of the film-center ray."""
    sensor = _load_sensor(sensor_dict)
    ray, _ = sensor.sample_ray(0, 0, (0.5, 0.5), (0.5, 0.5))
    return Vector(list(ray.o)), Vector(list(ray.d))


def _view_frame_center_world(b_camera):
    """World-space center of Blender's camera view frame."""
    frame = b_camera.data.view_frame(scene=bpy.context.scene)
    center = sum(frame, Vector()) / 4
    return b_camera.matrix_world @ center


def test_perspective_defaults(mi_addon, fresh_scene):
    camera = _camera()
    camera.data.clip_start = 0.25
    camera.data.clip_end = 250.0
    sensor = _sensor_dict(_export_scene_dict())

    assert sensor['type'] == 'perspective'
    assert sensor['fov_axis'] == 'x'
    assert sensor['fov'] == pytest.approx(math.degrees(camera.data.angle_x))
    assert sensor['near_clip'] == pytest.approx(0.25)
    assert sensor['far_clip'] == pytest.approx(250.0)
    assert sensor['principal_point_offset_x'] == 0.0
    assert sensor['principal_point_offset_y'] == 0.0
    assert _load_sensor(sensor) is not None


def test_vertical_sensor_fit_uses_y_axis(mi_addon, fresh_scene):
    camera = _camera()
    camera.data.sensor_fit = 'VERTICAL'
    sensor = _sensor_dict(_export_scene_dict())

    assert sensor['fov_axis'] == 'y'
    assert sensor['fov'] == pytest.approx(math.degrees(camera.data.angle_y))


def test_portrait_resolution_uses_y_axis(mi_addon, fresh_scene):
    scene = bpy.context.scene
    scene.render.resolution_x = 480
    scene.render.resolution_y = 640
    camera = _camera()
    sensor = _sensor_dict(_export_scene_dict())

    # With AUTO fit the 36mm sensor width applies to the larger (vertical)
    # dimension, so the vertical field of view is angle_x.
    assert sensor['fov_axis'] == 'y'
    assert sensor['fov'] == pytest.approx(math.degrees(camera.data.angle_x))


@pytest.mark.parametrize('res,sensor_fit', [
    ((640, 480), 'AUTO'),
    ((480, 640), 'AUTO'),
    ((640, 480), 'HORIZONTAL'),
    ((640, 480), 'VERTICAL'),
])
def test_perspective_corners_match_view_frame(mi_addon, fresh_scene, res,
                                              sensor_fit):
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = res
    camera = _camera()
    camera.data.sensor_fit = sensor_fit
    bpy.context.view_layer.update()

    mi_sensor = _load_sensor(_sensor_dict(_export_scene_dict()))
    frame = [camera.matrix_world @ v
             for v in camera.data.view_frame(scene=scene)]
    origin = camera.matrix_world.translation

    # Mitsuba film (0, 0) is the top-left corner (frame[3])
    corner_pairs = [((0, 0), frame[3]), ((1, 0), frame[0]),
                    ((0, 1), frame[2]), ((1, 1), frame[1])]
    for film_pos, corner in corner_pairs:
        ray, _ = mi_sensor.sample_ray(0, 0, film_pos, (0.5, 0.5))
        direction = Vector(list(ray.d))
        expected = (corner - origin).normalized()
        assert max(abs(a - b) for a, b in zip(direction, expected)) < 1e-4, \
            (film_pos, tuple(direction), tuple(expected))


def test_film_resolution_and_percentage(mi_addon, fresh_scene):
    scene = bpy.context.scene
    scene.render.resolution_x = 640
    scene.render.resolution_y = 360
    scene.render.resolution_percentage = 50
    sensor = _sensor_dict(_export_scene_dict())

    assert sensor['film']['width'] == 320
    assert sensor['film']['height'] == 180


@pytest.mark.parametrize('sensor_fit', ['AUTO', 'VERTICAL'])
def test_shift_matches_blender_view_frame(mi_addon, fresh_scene, sensor_fit):
    scene = bpy.context.scene
    scene.render.resolution_x = 640
    scene.render.resolution_y = 480
    camera = _camera()
    camera.data.sensor_fit = sensor_fit
    camera.data.shift_x = 0.2
    camera.data.shift_y = 0.1
    bpy.context.view_layer.update()

    sensor = _sensor_dict(_export_scene_dict())
    _, direction = _center_ray(sensor)

    center = _view_frame_center_world(camera)
    expected = (center - camera.matrix_world.translation).normalized()
    assert max(abs(a - b) for a, b in zip(direction, expected)) < 1e-4


def test_dof_exports_thinlens(mi_addon, fresh_scene):
    camera = _camera()
    camera.data.lens = 80.0
    camera.data.dof.use_dof = True
    camera.data.dof.aperture_fstop = 2.0
    camera.data.dof.focus_distance = 3.5
    sensor = _sensor_dict(_export_scene_dict())

    assert sensor['type'] == 'thinlens'
    # Cycles thin lens: radius = focal_length / (2 fstop), in meters
    assert sensor['aperture_radius'] == pytest.approx(0.08 / (2.0 * 2.0))
    assert sensor['focus_distance'] == pytest.approx(3.5)
    assert 'principal_point_offset_x' not in sensor
    assert _load_sensor(sensor) is not None


def test_dof_focus_object_distance(mi_addon, fresh_scene):
    camera = _camera()
    camera.data.dof.use_dof = True
    camera.data.dof.focus_object = bpy.data.objects['Cube']
    bpy.context.view_layer.update()
    sensor = _sensor_dict(_export_scene_dict())

    local = camera.matrix_world.inverted() @ \
        bpy.data.objects['Cube'].matrix_world.translation
    assert sensor['focus_distance'] == pytest.approx(abs(local.z), rel=1e-5)


def test_orthographic_extents_match_view_frame(mi_addon, fresh_scene):
    scene = bpy.context.scene
    scene.render.resolution_x = 640
    scene.render.resolution_y = 480
    camera = _camera()
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = 4.0
    camera.data.shift_x = 0.25
    camera.data.shift_y = -0.125
    bpy.context.view_layer.update()

    sensor = _sensor_dict(_export_scene_dict())
    assert sensor['type'] == 'orthographic'
    mi_sensor = _load_sensor(sensor)

    # The origins of the corner rays must land on Blender's view frame
    # corners (projected onto the camera plane).
    frame = [camera.matrix_world @ v
             for v in camera.data.view_frame(scene=scene)]
    view_dir = camera.matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0))

    # Mitsuba film (0, 0) is the top-left corner: max x, max y in the
    # Blender camera frame (frame[3] is the top-left corner).
    corner_pairs = [((0, 0), frame[3]), ((1, 0), frame[0]),
                    ((0, 1), frame[2]), ((1, 1), frame[1])]
    for film_pos, expected in corner_pairs:
        ray, _ = mi_sensor.sample_ray(0, 0, film_pos, (0.5, 0.5))
        origin = Vector(list(ray.o))
        # Compare in the camera plane (the ray starts at the near clip)
        delta = origin - expected
        delta -= delta.dot(view_dir) * view_dir
        assert delta.length < 1e-4, (film_pos, tuple(origin), tuple(expected))


def test_panoramic_falls_back_to_perspective(mi_addon, fresh_scene):
    camera = _camera()
    camera.data.type = 'PANO'
    sensor = _sensor_dict(_export_scene_dict())
    assert sensor['type'] == 'perspective'
