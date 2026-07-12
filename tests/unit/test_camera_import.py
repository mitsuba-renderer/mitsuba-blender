"""Camera import through convert.importer.camera."""

import math

import bpy
import pytest


def _import_sensor_xml(tmp_path, sensor_body, width=640, height=480):
    xml = f'''<scene version="3.0.0">
        {sensor_body}
    </scene>'''
    scene_file = tmp_path / 'scene.xml'
    scene_file.write_text(xml)
    assert bpy.ops.import_scene.mitsuba(filepath=str(scene_file)) == \
        {'FINISHED'}
    return bpy.context.scene.camera


FILM = '<film type="hdrfilm">' \
       '<integer name="width" value="640"/>' \
       '<integer name="height" value="480"/></film>'


def test_perspective_fov_x(mi_addon, fresh_scene, tmp_path):
    camera = _import_sensor_xml(tmp_path, f'''
        <sensor type="perspective">
            <string name="fov_axis" value="x"/>
            <float name="fov" value="40.0"/>
            <float name="near_clip" value="0.5"/>
            <float name="far_clip" value="500.0"/>
            {FILM}
        </sensor>''')

    assert camera is not None
    assert camera.data.type == 'PERSP'
    assert camera.data.angle_x == pytest.approx(math.radians(40.0), rel=1e-5)
    assert camera.data.clip_start == pytest.approx(0.5)
    assert camera.data.clip_end == pytest.approx(500.0)


def test_perspective_fov_y(mi_addon, fresh_scene, tmp_path):
    camera = _import_sensor_xml(tmp_path, f'''
        <sensor type="perspective">
            <string name="fov_axis" value="y"/>
            <float name="fov" value="30.0"/>
            {FILM}
        </sensor>''')

    # Horizontal fov for a 4:3 film with a 30 degree vertical fov
    expected = 2.0 * math.atan(math.tan(math.radians(15.0)) * 640.0 / 480.0)
    assert camera.data.angle_x == pytest.approx(expected, rel=1e-5)


def test_perspective_focal_length(mi_addon, fresh_scene, tmp_path):
    # The focal_length parameter did not reach the Blender camera at all
    # in the old importer (it was assigned to the Mitsuba properties).
    camera = _import_sensor_xml(tmp_path, f'''
        <sensor type="perspective">
            <string name="focal_length" value="50mm"/>
            {FILM}
        </sensor>''')

    # Mitsuba interprets the focal length on the diagonal of a full-frame
    # 35mm sensor.
    tan_half_diag = math.hypot(36.0, 24.0) / (2.0 * 50.0)
    expected = 2.0 * math.atan(
        tan_half_diag * 640.0 / math.hypot(640.0, 480.0))
    assert camera.data.angle_x == pytest.approx(expected, rel=1e-5)


def test_perspective_shift(mi_addon, fresh_scene, tmp_path):
    # The old importer copied the principal point offset verbatim, without
    # the resolution scaling or the y sign flip.
    camera = _import_sensor_xml(tmp_path, f'''
        <sensor type="perspective">
            <float name="fov" value="40.0"/>
            <float name="principal_point_offset_x" value="0.2"/>
            <float name="principal_point_offset_y" value="-0.13333333"/>
            {FILM}
        </sensor>''')

    assert camera.data.shift_x == pytest.approx(0.2, rel=1e-5)
    assert camera.data.shift_y == pytest.approx(0.1, rel=1e-5)


def test_thinlens(mi_addon, fresh_scene, tmp_path):
    camera = _import_sensor_xml(tmp_path, f'''
        <sensor type="thinlens">
            <float name="fov" value="40.0"/>
            <float name="aperture_radius" value="0.02"/>
            <float name="focus_distance" value="3.5"/>
            {FILM}
        </sensor>''')

    assert camera.data.dof.use_dof
    assert camera.data.dof.focus_distance == pytest.approx(3.5)
    expected_fstop = camera.data.lens / (2.0 * 0.02) / 1000.0
    assert camera.data.dof.aperture_fstop == pytest.approx(expected_fstop,
                                                           rel=1e-5)


def test_orthographic(mi_addon, fresh_scene, tmp_path):
    camera = _import_sensor_xml(tmp_path, f'''
        <sensor type="orthographic">
            <transform name="to_world">
                <scale x="2.0" y="2.0" z="1.0"/>
                <translate x="1.0" y="2.0" z="3.0"/>
            </transform>
            {FILM}
        </sensor>''')

    assert camera.data.type == 'ORTHO'
    assert camera.data.ortho_scale == pytest.approx(4.0, rel=1e-5)
    # The view scale must not leak into the object transform
    scale = camera.matrix_world.decompose()[2]
    assert max(abs(s - 1.0) for s in scale) < 1e-5


def test_unsupported_sensor_is_skipped(mi_addon, fresh_scene, tmp_path):
    camera = _import_sensor_xml(tmp_path, f'''
        <sensor type="irradiancemeter">
            {FILM}
        </sensor>''')
    assert camera is None
