"""The importer must never raise for unsupported content: it produces
placeholders and collects warnings that the operator reports."""

import bpy


def _write_scene(tmp_path, xml_body):
    scene_file = tmp_path / 'scene.xml'
    scene_file.write_text(f'<scene version="3.0.0">\n{xml_body}\n</scene>')
    return scene_file


UNKNOWN_SHAPE = '''
    <shape type="frobnicator">
        <float name="x" value="1.0"/>
    </shape>'''


def test_unknown_shape_yields_placeholder(mi_addon, fresh_scene, tmp_path):
    scene_file = _write_scene(tmp_path, UNKNOWN_SHAPE)
    assert bpy.ops.import_scene.mitsuba(filepath=str(scene_file)) == \
        {'FINISHED'}

    # The failed shape is kept as an empty placeholder mesh object
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
    assert len(meshes) == 1
    assert len(meshes[0].data.vertices) == 0


def test_load_scene_collects_warnings(mi_addon, fresh_scene, tmp_path):
    from bl_ext.user_default.mitsuba_blender.io import importer, bl_utils
    from bpy_extras.io_utils import axis_conversion

    scene_file = _write_scene(tmp_path, UNKNOWN_SHAPE)
    axis_mat = axis_conversion(to_forward='-Z', to_up='Y').to_4x4()
    scene = bl_utils.init_empty_scene(bpy.context, name='warn-test')

    warnings = importer.load_mitsuba_scene(
        bpy.context, scene, scene.collection, str(scene_file), axis_mat,
        False, True)
    assert any('frobnicator' in w for w in warnings)


def test_missing_mesh_file_yields_placeholder(mi_addon, fresh_scene,
                                              tmp_path):
    scene_file = _write_scene(tmp_path, '''
        <shape type="ply">
            <string name="filename" value="does-not-exist.ply"/>
        </shape>''')
    assert bpy.ops.import_scene.mitsuba(filepath=str(scene_file)) == \
        {'FINISHED'}
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
    assert len(meshes) == 1
    assert len(meshes[0].data.vertices) == 0


def test_multiple_rfilters_use_first(mi_addon, fresh_scene, tmp_path):
    scene_file = _write_scene(tmp_path, '''
        <sensor type="perspective">
            <film type="hdrfilm">
                <rfilter type="gaussian"/>
                <rfilter type="box"/>
            </film>
        </sensor>''')
    assert bpy.ops.import_scene.mitsuba(filepath=str(scene_file)) == \
        {'FINISHED'}


def test_unknown_film_does_not_abort(mi_addon, fresh_scene, tmp_path):
    scene_file = _write_scene(tmp_path, '''
        <sensor type="perspective">
            <film type="specfilm"/>
        </sensor>''')
    assert bpy.ops.import_scene.mitsuba(filepath=str(scene_file)) == \
        {'FINISHED'}
    assert bpy.context.scene.camera is not None


def test_converter_exception_does_not_abort(mi_addon, fresh_scene, tmp_path,
                                            monkeypatch):
    # Shape and sensor converters run under the same never-crash contract
    # as materials: an exception must degrade to a warning
    import sys
    importer = sys.modules[mi_addon].io.importer
    from bl_ext.user_default.mitsuba_blender.io import bl_utils
    from bpy_extras.io_utils import axis_conversion

    def boom(mi_context, node_id):
        raise RuntimeError('boom')
    monkeypatch.setattr(importer, 'convert_mi_shape', boom)

    scene_file = _write_scene(tmp_path, '''
        <shape type="rectangle">
            <bsdf type="diffuse"/>
        </shape>''')
    axis_mat = axis_conversion(to_forward='-Z', to_up='Y').to_4x4()
    scene = bl_utils.init_empty_scene(bpy.context, name='guard-test')

    warnings = importer.load_mitsuba_scene(
        bpy.context, scene, scene.collection, str(scene_file), axis_mat,
        False, True)
    assert any('boom' in w for w in warnings)


def test_failed_parse_preserves_scene(mi_addon, fresh_scene, tmp_path):
    # A malformed XML file must not destroy the user's scene: the file is
    # parsed before any destructive scene change happens.
    scene_file = tmp_path / 'broken.xml'
    scene_file.write_text('<scene version="3.0.0">\n<shape')

    names_before = {obj.name for obj in bpy.data.objects}
    assert 'Cube' in names_before

    try:
        result = bpy.ops.import_scene.mitsuba(filepath=str(scene_file))
    except RuntimeError:
        result = {'CANCELLED'}
    assert result == {'CANCELLED'}
    assert {obj.name for obj in bpy.data.objects} == names_before
    assert bpy.data.meshes


def test_clean_scene_has_no_warnings(mi_addon, fresh_scene, tmp_path):
    from bl_ext.user_default.mitsuba_blender.io import importer, bl_utils
    from bpy_extras.io_utils import axis_conversion

    scene_file = _write_scene(tmp_path, '''
        <shape type="rectangle">
            <bsdf type="diffuse"/>
        </shape>''')
    axis_mat = axis_conversion(to_forward='-Z', to_up='Y').to_4x4()
    scene = bl_utils.init_empty_scene(bpy.context, name='clean-test')

    warnings = importer.load_mitsuba_scene(
        bpy.context, scene, scene.collection, str(scene_file), axis_mat,
        False, True)
    assert warnings == []


def test_second_import_keeps_previous_import(mi_addon, fresh_scene,
                                             tmp_path):
    # Importing into a new scene used to delete an existing 'Mitsuba'
    # scene and purge its data, silently destroying the previous import
    scene_file = _write_scene(tmp_path, '''
        <shape type="rectangle">
            <bsdf type="diffuse"/>
        </shape>''')

    assert bpy.ops.import_scene.mitsuba(
        filepath=str(scene_file), override_scene=False) == {'FINISHED'}
    first_name = bpy.context.window.scene.name
    first_objs = {o.name for o in bpy.context.window.scene.objects}
    assert first_objs

    assert bpy.ops.import_scene.mitsuba(
        filepath=str(scene_file), override_scene=False) == {'FINISHED'}
    second_name = bpy.context.window.scene.name

    assert second_name != first_name
    assert first_name in bpy.data.scenes
    assert {o.name for o in bpy.data.scenes[first_name].objects} == \
        first_objs
