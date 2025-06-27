import bpy

from mathutils import Matrix

def test_sensor():
    import importlib
    sensors = importlib.import_module("mitsuba-blender.importer.sensors")
    assert sensors
    common = importlib.import_module("mitsuba-blender.importer.common")
    assert common

    from mitsuba import Properties
    sensor_names = {
        'perspective': 'PERSP',
        'orthographic': 'ORTHO'
    }
    for mi_name, bl_name in sensor_names.items():
        mi_sensor_props = Properties(mi_name)
        mi_context = common.MitsubaSceneImportContext(bpy.context, bpy.context.scene, bpy.context.scene.collection, mi_sensor_props, Matrix())

        bl_camera, world_matrix = sensors.mi_sensor_to_bl_camera(mi_context, mi_sensor_props)
        assert bl_camera.type == bl_name
