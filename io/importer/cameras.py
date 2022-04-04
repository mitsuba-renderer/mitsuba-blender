import math

if "bpy" in locals():
    import importlib
    if "bl_transform_utils" in locals():
        importlib.reload(bl_transform_utils)

import bpy
from mathutils import Matrix

from . import bl_transform_utils

######################
##    Converters    ##
######################

def mi_perspective_to_bl_camera(mi_context, mi_sensor):
    bl_camera = bpy.data.cameras.new(name=mi_sensor.id())
    bl_camera.type = 'PERSP'
    
    bl_camera.clip_start = mi_sensor.get('near_clip', 1e-2)
    bl_camera.clip_end = mi_sensor.get('far_clip', 1e4)

    bl_camera.shift_x = mi_sensor.get('principal_point_offset_x', 0.0)
    bl_camera.shift_y = mi_sensor.get('principal_point_offset_y', 0.0)

    if mi_sensor.has_property('focal_length'):
        mi_sensor.lens = mi_sensor.get('focal_length', 50)
    else:
        fov_axis = mi_sensor.get('fov_axis', 'x')
        fov = math.radians(mi_sensor.get('fov', 80))
        if fov_axis == 'x':
            bl_camera.angle_x = fov
        elif fov_axis == 'y':
            bl_camera.angle_y = fov
        else:
            mi_context.log(f'Camera fov axis "{fov_axis}" not supported.', 'ERROR')

    # NOTE: Cameras are exported with a 180° rotation on the Y axis to be compatible with Mitsuba.
    #       Therefore, we need to reverse this rotation
    initial_rotation = Matrix.Rotation(-math.pi, 4, 'Y')
    world_matrix = bl_transform_utils.mi_transform_to_bl_transform(mi_sensor.get('to_world', None))

    return bl_camera, mi_context.mi_space_to_bl_space(world_matrix @ initial_rotation)

######################
##   Main import    ##
######################

_sensor_converters = {
    'perspective': mi_perspective_to_bl_camera,
}

def mi_sensor_to_bl_camera(mi_context, mi_sensor):
    sensor_type = mi_sensor.plugin_name()
    if sensor_type not in _sensor_converters:
        mi_context.log(f'Mitsuba Sensor type "{sensor_type}" not supported.', 'ERROR')
        return None
    
    # Create the Blender object
    bl_camera, world_matrix = _sensor_converters[sensor_type](mi_context, mi_sensor)

    return bl_camera, world_matrix
