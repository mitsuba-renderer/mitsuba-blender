import bpy

import pytest

from fixtures import *

@pytest.mark.parametrize("xml_scene", ["scenes/empty.xml"])
def test_importer_initializes_mitsuba_renderer(resource_resolver, xml_scene):
    scene_file = resource_resolver.get_absolute_resource_path(xml_scene)
    
    assert bpy.ops.mitsuba.scene_import(filepath=scene_file) == {'FINISHED'}

    assert bpy.context.scene.render.engine == 'MITSUBA'
    assert bpy.context.scene.mitsuba.variant == 'scalar_rgb'

@pytest.mark.parametrize("xml_scene", ["scenes/empty.xml"])
def test_importer_override_current_scene_conserves_name(resource_resolver, xml_scene):
    scene_file = resource_resolver.get_absolute_resource_path(xml_scene)

    assert len(bpy.data.scenes) == 1
    scene_name_before = bpy.data.scenes[0].name

    assert bpy.ops.mitsuba.scene_import(filepath=scene_file, override_scene=True) == {'FINISHED'}

    assert len(bpy.data.scenes) == 1
    assert bpy.data.scenes[0].name == scene_name_before

@pytest.mark.parametrize("xml_scene", ["scenes/empty.xml"])
def test_importer_multiple_scene_imports(resource_resolver, xml_scene):
    scene_file = resource_resolver.get_absolute_resource_path(xml_scene)

    assert len(bpy.data.scenes) == 1

    assert bpy.ops.mitsuba.scene_import(filepath=scene_file, override_scene=False) == {'FINISHED'}
    object_count_before = len(bpy.context.scene.objects)

    assert len(bpy.data.scenes) == 2

    assert bpy.ops.mitsuba.scene_import(filepath=scene_file, override_scene=False) == {'FINISHED'}
    assert len(bpy.context.scene.objects) == object_count_before

    assert len(bpy.data.scenes) == 2

@pytest.mark.parametrize("xml_scene", ["scenes/empty.xml"])
def test_importer_multiple_scene_import_override(resource_resolver, xml_scene):
    scene_file = resource_resolver.get_absolute_resource_path(xml_scene)

    assert len(bpy.data.scenes) == 1

    assert bpy.ops.mitsuba.scene_import(filepath=scene_file, override_scene=True) == {'FINISHED'}
    object_count_before = len(bpy.context.scene.objects)

    assert len(bpy.data.scenes) == 1

    assert bpy.ops.mitsuba.scene_import(filepath=scene_file, override_scene=True) == {'FINISHED'}
    assert len(bpy.context.scene.objects) == object_count_before

    assert len(bpy.data.scenes) == 1

@pytest.mark.parametrize("xml_scene", ["scenes/empty.xml"])
def test_importer_set_new_scene_as_active(resource_resolver, xml_scene):
    scene_file = resource_resolver.get_absolute_resource_path(xml_scene)

    assert len(bpy.data.scenes) == 1
    scene_name_before = bpy.data.scenes[0].name

    assert bpy.ops.mitsuba.scene_import(filepath=scene_file, override_scene=False) == {'FINISHED'}

    assert len(bpy.data.scenes) == 2
    assert bpy.context.scene.name != scene_name_before
