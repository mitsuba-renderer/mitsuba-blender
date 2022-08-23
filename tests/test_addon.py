import bpy

from mathutils import Matrix

def test_prespective_sensor():
    import importlib
    sensors = importlib.import_module("mitsuba-blender.io.importer.sensors")
    assert sensors
    common = importlib.import_module("mitsuba-blender.io.importer.common")
    assert common

    from mitsuba import Properties
    mi_sensor_props = Properties('perspective')
    mi_context = common.MitsubaSceneImportContext(bpy.context, bpy.context.scene, bpy.context.scene.collection, '', mi_sensor_props, Matrix())

    bl_camera, world_matrix = sensors.mi_perspective_to_bl_camera(mi_context, mi_sensor_props)
    assert bl_camera.type == 'PERSP'
