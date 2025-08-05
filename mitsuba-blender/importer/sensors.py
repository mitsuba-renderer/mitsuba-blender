import bpy
import math
from mathutils import Matrix

from . import bl_transform_utils
from . import mi_props_utils
from .. import logging

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

    film_aspect = None
    film = mi_props_utils.named_references_with_class(mi_context, mi_sensor, 'Film')[0][1]
    film_aspect = film['width'] / film['height']

    if mi_sensor.has_property('focal_length'):
        mi_sensor.lens = mi_sensor.get('focal_length', 50)
    else:
        fov_axis = mi_sensor.get('fov_axis', 'x')

        if fov_axis == 'smaller':
            fov_axis = 'y' if film_aspect > 1 else 'x'
        elif fov_axis == 'larger':
            fov_axis = 'x' if film_aspect > 1 else 'y'

        fov = math.radians(mi_sensor.get('fov', 80))
        if fov_axis == 'x':
            bl_camera.angle_x = fov
        elif fov_axis == 'y':
            bl_camera.angle_y = fov
        else:
            logging.error(f'Camera fov axis "{fov_axis}" not supported.')

    # NOTE: Cameras are exported with a 180° rotation on the Y axis to be compatible with Mitsuba.
    #       Therefore, we need to reverse this rotation
    initial_rotation = Matrix.Rotation(-math.pi, 4, 'Y')
    world_matrix = bl_transform_utils.mi_transform_to_bl_transform(mi_sensor.get('to_world', None))

    return bl_camera, mi_context.mi_space_to_bl_space(world_matrix @ initial_rotation)

def mi_orthographic_to_bl_camera(mi_context, mi_sensor):
    import drjit as dr
    import mitsuba as mi
    bl_camera = bpy.data.cameras.new(name=mi_sensor.id())
    bl_camera.type = 'ORTHO'

    bl_camera.clip_start = mi_sensor.get('near_clip', 1e-3)
    bl_camera.clip_end   = mi_sensor.get('far_clip',  1e4)

    bl_camera.shift_x = 0.0
    bl_camera.shift_y = 0.0

    bl_camera.ortho_scale = 2.0

    to_world = mi_sensor.get('to_world', None)
    if to_world is not None:
        s, q, tr = dr.transform_decompose(to_world.matrix)
        scale = dr.norm(dr.diag(s))
        bl_camera.ortho_scale *= scale
        s /= scale
        to_world = mi.ScalarTransform4f(dr.transform_compose(s, q, tr))

    initial_rotation = Matrix.Rotation(-math.pi, 4, 'Y')
    world_matrix = bl_transform_utils.mi_transform_to_bl_transform(to_world)

    return bl_camera, mi_context.mi_space_to_bl_space(world_matrix @ initial_rotation)

######################
##   Main import    ##
######################

_sensor_converters = {
    'perspective':  mi_perspective_to_bl_camera,
    'orthographic': mi_orthographic_to_bl_camera,
}

def mi_sensor_to_bl_camera(mi_context, mi_sensor):
    sensor_type = mi_sensor.plugin_name()
    if sensor_type not in _sensor_converters:
        logging.error(f'Mitsuba Sensor type "{sensor_type}" not supported.')
        return None

    # Create the Blender object
    bl_camera, world_matrix = _sensor_converters[sensor_type](mi_context, mi_sensor)

    return bl_camera, world_matrix
