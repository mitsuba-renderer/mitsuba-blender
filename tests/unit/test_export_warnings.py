"""Export warnings are collected and reported after the export."""

import sys

import bpy


def _scene_converter(mi_addon, render=False):
    from bl_ext.user_default.mitsuba_blender.io.exporter import SceneConverter
    return SceneConverter(render=render)


def test_export_collects_warnings(mi_addon, fresh_scene, tmp_path):
    # Armatures are not exportable and must produce a warning
    bpy.ops.object.armature_add()
    armature_name = bpy.context.object.name_full

    converter = _scene_converter(mi_addon)
    converter.export_ctx.directory = str(tmp_path)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    converter.scene_to_dict(depsgraph)

    warnings = converter.export_ctx.warnings
    assert warnings
    assert any(armature_name in message for message in warnings)


def test_clean_export_has_no_warnings(mi_addon, fresh_scene, tmp_path):
    converter = _scene_converter(mi_addon)
    converter.export_ctx.directory = str(tmp_path)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    converter.scene_to_dict(depsgraph)
    assert converter.export_ctx.warnings == []


def test_f12_with_warnings_still_renders(mi_addon, fresh_scene, tmp_path):
    scene = fresh_scene
    bpy.ops.object.armature_add()
    scene.render.engine = 'MITSUBA'
    scene.mitsuba.variant = 'scalar_rgb'
    scene.render.resolution_x = 32
    scene.render.resolution_y = 32
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(tmp_path / 'render.exr')
    scene.render.image_settings.file_format = 'OPEN_EXR'

    assert bpy.ops.render.render(write_still=True) == {'FINISHED'}
    assert (tmp_path / 'render.exr').exists()


def test_export_operator_reports_warnings(mi_addon, fresh_scene, tmp_path,
                                          capfd):
    bpy.ops.object.armature_add()
    filepath = str(tmp_path / 'scene.xml')
    assert bpy.ops.export_scene.mitsuba(filepath=filepath) == {'FINISHED'}

    # In background mode operator reports go to stdout
    captured = capfd.readouterr()
    assert 'exported with' in captured.out
    assert 'warnings' in captured.out
