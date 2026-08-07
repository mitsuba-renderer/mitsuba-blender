"""File placement of the scene exporter and the render engine.

Meshes and textures must land in subfolders of the export target directory
(or a temporary directory during rendering), never in the current working
directory.
"""

import os
from contextlib import contextmanager

import bpy


@contextmanager
def chdir(path):
    old_cwd = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_cwd)


def test_export_writes_into_target_dir(mi_addon, fresh_scene, tmp_path):
    target = tmp_path / 'export'
    target.mkdir()
    cwd = tmp_path / 'cwd'
    cwd.mkdir()

    xml_file = target / 'scene.xml'
    with chdir(cwd):
        result = bpy.ops.export_scene.mitsuba(filepath=str(xml_file))
    assert result == {'FINISHED'}

    assert xml_file.is_file()
    mesh_files = list((target / 'meshes').glob('*.serialized'))
    assert len(mesh_files) == 1
    # Nothing may leak into the current working directory
    assert list(cwd.iterdir()) == []

    # The exported XML must be loadable, i.e. its file references resolve
    import mitsuba as mi
    mi.set_variant('scalar_rgb')
    scene = mi.load_file(str(xml_file))
    assert scene.shapes()


def test_render_leaves_cwd_clean(mi_addon, fresh_scene, tmp_path):
    scene = fresh_scene
    scene.render.engine = 'MITSUBA'
    scene.mitsuba.variant = 'scalar_rgb'
    scene.render.resolution_x = 32
    scene.render.resolution_y = 32
    scene.render.resolution_percentage = 100

    cwd = tmp_path / 'cwd'
    cwd.mkdir()
    with chdir(cwd):
        assert bpy.ops.render.render() == {'FINISHED'}
    assert list(cwd.iterdir()) == []
