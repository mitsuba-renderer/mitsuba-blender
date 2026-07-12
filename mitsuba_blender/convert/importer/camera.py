'''Mitsuba sensor to Blender camera conversion.

The geometric mappings are the inverses of the ones defined in
convert.export.camera. Imported cameras always use the AUTO sensor fit,
so the fit axis is the larger film dimension.
'''

import math

import bpy
from mathutils import Matrix

from ..export.camera import (extent_to_ortho_scale, aperture_radius_to_fstop,
                             principal_point_to_shift)
from ...io.importer.bl_transform_utils import mi_transform_to_bl_transform

# The diagonal of a full-frame 35mm sensor (36x24), which Mitsuba uses to
# interpret its focal_length parameter.
FULLFRAME_DIAGONAL = math.hypot(36.0, 24.0)


######################
##    Utilities     ##
######################

def _film_size(mi_context, mi_sensor):
    '''The resolution of the sensor's film, falling back to Mitsuba's
    default film size.'''
    from mitsuba import ObjectType, Properties
    for _, value in mi_sensor.items():
        if isinstance(value, Properties.ResolvedReference):
            mi_node = mi_context.mi_state.nodes[value.index()]
            if mi_node.type == ObjectType.Film:
                return (mi_node.props.get('width', 768),
                        mi_node.props.get('height', 576))
    return 768, 576


def _angle_x_from_fov(mi_context, mi_sensor, res_x, res_y):
    '''The horizontal field of view in radians, from either the fov/fov_axis
    or the focal_length parametrization.'''
    if 'focal_length' in mi_sensor:
        # A focal length is relative to the diagonal of a full-frame sensor
        focal_length = str(mi_sensor['focal_length'])
        value = float(focal_length.replace('mm', ''))
        tan_half = FULLFRAME_DIAGONAL / (2.0 * value)
        axis = 'diagonal'
    else:
        tan_half = math.tan(math.radians(mi_sensor.get('fov', 34.0)) / 2.0)
        axis = mi_sensor.get('fov_axis', 'x')

    if axis == 'smaller':
        axis = 'x' if res_x <= res_y else 'y'
    elif axis == 'larger':
        axis = 'x' if res_x >= res_y else 'y'

    if axis == 'y':
        tan_half *= res_x / res_y
    elif axis == 'diagonal':
        tan_half *= res_x / math.hypot(res_x, res_y)
    elif axis != 'x':
        mi_context.log(f'Camera fov axis "{axis}" is not supported. '
                       'Assuming "x".', 'WARN')
    return 2.0 * math.atan(tan_half)


def _set_angle(bl_camera, angle_x, res_x, res_y):
    '''Assign the field of view to the axis that the AUTO sensor fit locks.'''
    if res_x >= res_y:
        bl_camera.angle_x = angle_x
    else:
        # The 36mm sensor width applies to the vertical axis (see the
        # exporter), so the vertical field of view lands in angle_x.
        bl_camera.angle_x = 2.0 * math.atan(
            math.tan(angle_x / 2.0) * res_y / res_x)


def _world_matrix(mi_context, mi_sensor):
    '''Undo the 180 degree Y rotation that distinguishes a Mitsuba sensor
    frame from a Blender camera frame.'''
    init_rot = Matrix.Rotation(-math.pi, 4, 'Y')
    world = mi_transform_to_bl_transform(mi_sensor.get('to_world', None))
    return mi_context.mi_space_to_bl_space(world @ init_rot)


######################
##    Converters    ##
######################

def _perspective_to_bl_camera(mi_context, mi_sensor):
    res_x, res_y = _film_size(mi_context, mi_sensor)
    bl_camera = bpy.data.cameras.new(name=mi_sensor.id())
    bl_camera.type = 'PERSP'
    _set_angle(bl_camera, _angle_x_from_fov(mi_context, mi_sensor,
                                            res_x, res_y), res_x, res_y)
    bl_camera.shift_x, bl_camera.shift_y = principal_point_to_shift(
        mi_sensor.get('principal_point_offset_x', 0.0),
        mi_sensor.get('principal_point_offset_y', 0.0), res_x, res_y)
    return bl_camera, _world_matrix(mi_context, mi_sensor)


def _thinlens_to_bl_camera(mi_context, mi_sensor):
    bl_camera, world_matrix = _perspective_to_bl_camera(mi_context, mi_sensor)
    bl_camera.dof.use_dof = True
    bl_camera.dof.focus_distance = mi_sensor.get('focus_distance', 0.0)
    aperture_radius = mi_sensor.get('aperture_radius', 0.1)
    bl_camera.dof.aperture_fstop = aperture_radius_to_fstop(
        aperture_radius, bl_camera.lens)
    return bl_camera, world_matrix


def _orthographic_to_bl_camera(mi_context, mi_sensor):
    res_x, res_y = _film_size(mi_context, mi_sensor)
    bl_camera = bpy.data.cameras.new(name=mi_sensor.id())
    bl_camera.type = 'ORTHO'

    world_matrix = _world_matrix(mi_context, mi_sensor)
    # The view extent is a scale in to_world; it becomes the orthographic
    # scale rather than part of the object transform.
    location, rotation, scale = world_matrix.decompose()
    bl_camera.ortho_scale = extent_to_ortho_scale(scale.x, res_x, res_y)
    return bl_camera, Matrix.LocRotScale(location, rotation, None)


######################
##   Main import    ##
######################

_converters = {
    'perspective': _perspective_to_bl_camera,
    'thinlens': _thinlens_to_bl_camera,
    'orthographic': _orthographic_to_bl_camera,
}


def mi_sensor_to_bl_camera(mi_context, mi_sensor):
    '''Convert a Mitsuba sensor into a Blender camera data-block and its
    world matrix. Returns None for unsupported sensor types.'''
    converter = _converters.get(mi_sensor.plugin_name())
    if converter is None:
        mi_context.log(f'Mitsuba sensor type "{mi_sensor.plugin_name()}" is '
                       'not supported.', 'WARN')
        return None

    bl_camera, world_matrix = converter(mi_context, mi_sensor)
    bl_camera.clip_start = mi_sensor.get('near_clip', 1e-2)
    bl_camera.clip_end = mi_sensor.get('far_clip', 1e4)
    return bl_camera, world_matrix
