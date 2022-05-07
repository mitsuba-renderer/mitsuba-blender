import math

if "bpy" in locals():
    import importlib
    if "bl_transform_utils" in locals():
        importlib.reload(bl_transform_utils)
    if "mi_spectra_utils" in locals():
        importlib.reload(mi_spectra_utils)

import bpy
from mathutils import Matrix, Vector

from . import bl_transform_utils
from . import mi_spectra_utils

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
    from mitsuba import Properties
    if mi_emitter.has_property(mi_prop_name):
        mi_prop_type = mi_emitter.type(mi_prop_name)
        if mi_prop_type == Properties.Type.Color:
            return mi_spectra_utils.get_color_strength_from_radiance(mi_emitter.get(mi_prop_name))
        if mi_prop_type == Properties.Type.Object:
            return mi_spectra_utils.convert_mi_srgb_emitter_spectrum(mi_emitter.get(mi_prop_name), default)
        else:
            mi_context.log(f'Material property "{mi_prop_name}" of type "{mi_prop_type}" cannot be converted to float.', 'ERROR')
    elif default is not None:
        return mi_spectra_utils.get_color_strength_from_radiance(default)
    else:
        mi_context.log(f'Material "{mi_emitter.id()}" does not have property "{mi_prop_name}".', 'ERROR')

######################
##    Converters    ##
######################

def mi_point_to_bl_light(mi_context, mi_emitter):
    bl_light = bpy.data.lights.new(name=mi_emitter.id(), type='POINT')

    color, strength = _get_radiance_value(mi_context, mi_emitter, 'intensity', [10/(math.pi*4)]*3)
    bl_light.color = color
    bl_light.energy = strength * math.pi * 4
    bl_light.shadow_soft_size = 0
    
    if mi_emitter.has_property('to_world'):
        world_matrix = mi_context.mi_space_to_bl_space(bl_transform_utils.mi_transform_to_bl_transform(mi_emitter.get('to_world', None)))
    else:
        world_matrix = Matrix.Translation(mi_context.mi_space_to_bl_space(Vector(mi_emitter.get('position', [0.0, 0.0, 0.0]))))

    return bl_light, world_matrix

def mi_directional_to_bl_light(mi_context, mi_emitter):
    bl_light = bpy.data.lights.new(name=mi_emitter.id(), type='SUN')

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

######################
##   Main import    ##
######################

_emitter_converters = {
    'point': mi_point_to_bl_light,
    'directional': mi_directional_to_bl_light,
}

def mi_emitter_to_bl_light(mi_context, mi_emitter):
    emitter_type = mi_emitter.plugin_name()
    if emitter_type not in _emitter_converters:
        mi_context.log(f'Mitsuba Emitter type "{emitter_type}" not supported.', 'ERROR')
        return None
    
    # Create the Blender object
    bl_light, world_matrix = _emitter_converters[emitter_type](mi_context, mi_emitter)

    return bl_light, world_matrix