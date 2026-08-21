"""Both export paths must place geometry in the same world coordinates.

Blender is Z-up and Mitsuba is Y-up. `export_ctx.axis_mat` carries that
conversion, and it was once set only by the export operator, so F12
rendered every scene rotated 90 degrees about X while the same scene
exported to XML was correct. Nothing in the suite noticed.

These tests pin the conversion itself and the agreement between the two
paths, so a caller that forgets to set `axis_mat` fails here rather than
in a render.
"""

import math

import bpy
import numpy as np
import sys
import pytest

@pytest.fixture(scope='session')
def registry(mi_addon):
    return importlib.import_module(f'{mi_addon}.convert.export.materials')

@pytest.fixture
def offset_cube(fresh_scene):
    bpy.data.objects.remove(bpy.data.objects['Cube'])
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(1.0, 5.0, 3.0))
    return bpy.context.object


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



def _blender_to_mitsuba(v):
    """Blender (x, y, z) -> Mitsuba (x, z, -y), the -Z forward / Y up shift."""
    x, y, z = v
    return (x, z, -y)


def _bboxes(scene):
    """Shape bounding boxes, rounded and sorted so the order does not matter."""
    out = []
    for shape in scene.shapes():
        bbox = shape.bbox()
        out.append((tuple(round(c, 4) for c in bbox.min),
                    tuple(round(c, 4) for c in bbox.max)))
    return sorted(out)


@pytest.fixture
def offset_cube(fresh_scene):
    """A cube away from the origin, so a rotation about X is visible."""
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(1.0, 5.0, 3.0))
    return bpy.context.object


def test_render_and_file_paths_agree_on_geometry(offset_cube, exporter,
                                                 tmp_path):
    """The dict built for F12 and the one written to XML must place every
    shape identically. This is the check that a missing axis_mat fails."""
    import mitsuba as mi

    render_dir = tmp_path / 'render'
    file_dir = tmp_path / 'file'
    render_dir.mkdir()
    file_dir.mkdir()

    render_scene = exporter(render_dir, render=True).dict_to_scene()

    xml_path = file_dir / 'scene.xml'
    exporter(file_dir).dict_to_xml(str(xml_path))
    file_scene = mi.load_file(str(xml_path))

    assert _bboxes(render_scene) == _bboxes(file_scene)


def test_camera_orientation_matches_between_paths(offset_cube, exporter,
                                                  tmp_path):
    """A rotation about X leaves shape counts and sizes intact, so the
    sensor is worth checking on its own."""
    import mitsuba as mi

    render_dir = tmp_path / 'render'
    file_dir = tmp_path / 'file'
    render_dir.mkdir()
    file_dir.mkdir()

    render_scene = exporter(render_dir, render=True).dict_to_scene()

    xml_path = file_dir / 'scene.xml'
    exporter(file_dir).dict_to_xml(str(xml_path))
    file_scene = mi.load_file(str(xml_path))

    a = np.array(render_scene.sensors()[0].world_transform().matrix)
    b = np.array(file_scene.sensors()[0].world_transform().matrix)
    assert a == pytest.approx(b, abs=1e-5)
