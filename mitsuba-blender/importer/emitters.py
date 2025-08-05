import bpy

import math
from mathutils import Matrix, Vector

from . import bl_transform_utils
from . import mi_spectra_utils
from .. import logging

######################
##    Utilities     ##
######################

def _get_matrix_from_direction(direction, up):
    z = direction
    x = up.cross(z)
    # If `direction` is colinear with the `up` vector, we choose
    # `x` as an arbitrary orthogonal vector to `up`.
    if x.length_squared == 0:
        x = up.orthogonal()
    y = z.cross(x)

    x.normalize()
    y.normalize()
    z.normalize()

    rot = Matrix()
    rot[0][0] = x[0]
    rot[0][1] = y[0]
    rot[0][2] = z[0]
    rot[0][3] = 0
    rot[1][0] = x[1]
    rot[1][1] = y[1]
    rot[1][2] = z[1]
    rot[1][3] = 0
    rot[2][0] = x[2]
    rot[2][1] = y[2]
    rot[2][2] = z[2]
    rot[2][3] = 0

    return rot

def _get_radiance_value(mi_context, mi_emitter, mi_prop_name, default):
    import mitsuba as mi
    if mi_emitter.has_property(mi_prop_name):
        mi_prop_type = mi_emitter.type(mi_prop_name)
        if mi_prop_type == mi.Properties.Type.Color:
            return mi_spectra_utils.get_color_strength_from_radiance(mi_emitter.get(mi_prop_name))
        if mi_prop_type == mi.Properties.Type.Object:
            return mi_spectra_utils.convert_mi_srgb_emitter_spectrum(mi_emitter.get(mi_prop_name), default)
        else:
            logging.error(f'Material property "{mi_prop_name}" of type "{mi_prop_type}" cannot be converted to float.')
    elif default is not None:
        return mi_spectra_utils.get_color_strength_from_radiance(default)
    else:
        logging.error(f'Material "{mi_emitter.id()}" does not have property "{mi_prop_name}".')

######################
##    Converters    ##
######################

def mi_point_to_bl_light(mi_context, mi_emitter, mi_props_id):
    bl_light = bpy.data.lights.new(name=mi_props_id, type='POINT')

    color, strength = _get_radiance_value(mi_context, mi_emitter, 'intensity', [10/(math.pi*4)]*3)
    bl_light.color = color
    bl_light.energy = strength * math.pi * 4
    bl_light.shadow_soft_size = 0

    if mi_emitter.has_property('to_world'):
        world_matrix = mi_context.mi_space_to_bl_space(bl_transform_utils.mi_transform_to_bl_transform(mi_emitter.get('to_world', None)))
    else:
        world_matrix = Matrix.Translation(mi_context.mi_space_to_bl_space(Vector(mi_emitter.get('position', [0.0, 0.0, 0.0]))))

    return bl_light, world_matrix

def mi_directional_to_bl_light(mi_context, mi_emitter, mi_props_id):
    bl_light = bpy.data.lights.new(name=mi_props_id, type='SUN')

    color, strength = _get_radiance_value(mi_context, mi_emitter, 'irradiance', [1.0, 1.0, 1.0])
    bl_light.color = color
    bl_light.energy = strength

    rot_mat = Matrix.Rotation(-math.pi, 4, 'X')
    if mi_emitter.has_property('to_world'):
        world_matrix = bl_transform_utils.mi_transform_to_bl_transform(mi_emitter.get('to_world', None))
    elif mi_emitter.has_property('direction'):
        world_matrix = _get_matrix_from_direction(Vector(mi_emitter.get('direction', [0.0, 0.0, 1.0])), Vector([0.0, 1.0, 0.0]))
    else:
        world_matrix = Matrix()

    return bl_light, mi_context.mi_space_to_bl_space(world_matrix @ rot_mat)

def mi_area_to_bl_light(mi_context, mi_emitter, mi_props_id):
    bl_light = bpy.data.lights.new(name=mi_props_id, type='AREA')
    color, strength = _get_radiance_value(mi_context, mi_emitter, 'radiance', [1.0, 1.0, 1.0])
    bl_light.color = color
    bl_light.energy = strength
    world_matrix = Matrix()
    return bl_light, mi_context.mi_space_to_bl_space(world_matrix)

def mi_analytical_area_light(mi_context, mi_shape, mi_emitter, mi_props_id):
    bl_light, _ = mi_area_to_bl_light(mi_context, mi_emitter, mi_props_id)

    rot_mat = Matrix.Rotation(-math.pi, 4, 'X')
    if mi_shape.has_property('to_world'):
        world_matrix = bl_transform_utils.mi_transform_to_bl_transform(mi_shape.get('to_world', None))
    else:
        world_matrix = Matrix()

    # Mitsuba default disks and rectangles are twice as big as blender's
    scale_mat = Matrix.Scale(2.0, 4)
    world_matrix = world_matrix @ rot_mat @ scale_mat

    if mi_shape.plugin_name() == 'rectangle':
        bl_light.shape = 'RECTANGLE'
        bl_light.size   = 1.0
        bl_light.size_y = 1.0
    else:
        bl_light.shape = 'DISK'
        bl_light.size   = 1.0

    return bl_light, mi_context.mi_space_to_bl_space(world_matrix)

######################
##   Main import    ##
######################

_emitter_converters = {
    'point':       mi_point_to_bl_light,
    'directional': mi_directional_to_bl_light,
    'area':        mi_area_to_bl_light,
}

def mi_emitter_to_bl_light(mi_context, mi_emitter, mi_props_id):
    emitter_type = mi_emitter.plugin_name()
    if emitter_type not in _emitter_converters:
        logging.error(f'Mitsuba Emitter type "{emitter_type}" not supported.')
        return None

    # Create the Blender object
    bl_light, world_matrix = _emitter_converters[emitter_type](mi_context, mi_emitter, mi_props_id)

    return bl_light, world_matrix