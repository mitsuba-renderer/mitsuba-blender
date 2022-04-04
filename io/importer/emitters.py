import math

if "bpy" in locals():
    import importlib
    if "bl_transform_utils" in locals():
        importlib.reload(bl_transform_utils)

import bpy
from mathutils import Matrix, Vector

from . import bl_transform_utils

######################
##    Converters    ##
######################

def mi_point_to_bl_light(mi_context, mi_emitter):
    bl_light = bpy.data.lights.new(name=mi_emitter.id(), type='POINT')

    # TODO: Convert this to a color and energy value.
    intensity = mi_emitter.get('intensity', [1000/(math.pi*4)]*3)
    bl_light.energy = 1000
    
    if mi_emitter.has_property('to_world'):
        world_matrix = mi_context.mi_space_to_bl_space(bl_transform_utils.mi_transform_to_bl_transform(mi_emitter.get('to_world', None)))
    else:
        world_matrix = Matrix.Translation(mi_context.mi_space_to_bl_space(Vector(mi_emitter.get('position', [0.0, 0.0, 0.0]))))

    return bl_light, world_matrix

######################
##   Main import    ##
######################

_emitter_converters = {
    'point': mi_point_to_bl_light,
}

def mi_emitter_to_bl_light(mi_context, mi_emitter):
    emitter_type = mi_emitter.plugin_name()
    if emitter_type not in _emitter_converters:
        mi_context.log(f'Mitsuba Emitter type "{emitter_type}" not supported.', 'ERROR')
        return None
    
    # Create the Blender object
    bl_light, world_matrix = _emitter_converters[emitter_type](mi_context, mi_emitter)

    return bl_light, world_matrix