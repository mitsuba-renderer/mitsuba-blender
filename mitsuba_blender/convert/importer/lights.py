'''Mitsuba emitter to Blender light conversion.

The radiometric conversions are the inverses of the ones defined in
convert.export.lights, which is the single source of truth for the
Blender/Mitsuba unit correspondence.
'''

import math

import bpy
from mathutils import Matrix, Vector

from ..export.lights import (intensity_to_power, radiance_to_power,
                             sphere_area, spot_blend)
from ...io.importer import mi_spectra_utils
from ...io.importer.bl_transform_utils import mi_transform_to_bl_transform


######################
##    Utilities     ##
######################

def _light_name(mi_props):
    return mi_props.id() or f'Light-{mi_props.plugin_name()}'


def _direction_matrix(direction, up):
    '''A rotation matrix whose +Z axis points along `direction`.'''
    z = direction
    x = up.cross(z)
    # An arbitrary orthogonal vector when `direction` is collinear with `up`
    if x.length_squared == 0:
        x = up.orthogonal()
    y = z.cross(x)

    x.normalize()
    y.normalize()
    z.normalize()

    rot = Matrix()
    for i in range(3):
        rot[i][0], rot[i][1], rot[i][2] = x[i], y[i], z[i]
    return rot


# Blender point/spot/sun lights emit along -Z, Mitsuba emitters along +Z
_FLIP = Matrix.Rotation(math.pi, 4, 'X')


######################
##    Converters    ##
######################

def _convert_point(mi_context, mi_props):
    bl_light = bpy.data.lights.new(name=_light_name(mi_props), type='POINT')
    color, strength = mi_spectra_utils.convert_radiance_property(
        mi_context, mi_props, 'intensity', [1.0, 1.0, 1.0])
    bl_light.color = color
    bl_light.energy = intensity_to_power(strength)
    bl_light.shadow_soft_size = 0.0

    if 'to_world' in mi_props:
        matrix = mi_context.mi_space_to_bl_space(
            mi_transform_to_bl_transform(mi_props.get('to_world')))
    else:
        position = Vector(list(mi_props.get('position', [0.0, 0.0, 0.0])))
        matrix = Matrix.Translation(mi_context.mi_space_to_bl_space(position))
    return bl_light, matrix


def _convert_spot(mi_context, mi_props):
    bl_light = bpy.data.lights.new(name=_light_name(mi_props), type='SPOT')
    color, strength = mi_spectra_utils.convert_radiance_property(
        mi_context, mi_props, 'intensity', [1.0, 1.0, 1.0])
    bl_light.color = color
    bl_light.energy = intensity_to_power(strength)
    bl_light.shadow_soft_size = 0.0

    cutoff = math.radians(float(mi_props.get('cutoff_angle', 20.0)))
    beam_width = math.radians(
        float(mi_props.get('beam_width', math.degrees(cutoff) * 0.75)))
    bl_light.spot_size = 2.0 * cutoff
    bl_light.spot_blend = spot_blend(2.0 * cutoff, beam_width)

    matrix = mi_transform_to_bl_transform(mi_props.get('to_world', None))
    return bl_light, mi_context.mi_space_to_bl_space(matrix @ _FLIP)


def _convert_directional(mi_context, mi_props):
    bl_light = bpy.data.lights.new(name=_light_name(mi_props), type='SUN')
    color, strength = mi_spectra_utils.convert_radiance_property(
        mi_context, mi_props, 'irradiance', [1.0, 1.0, 1.0])
    bl_light.color = color
    # The energy of a Blender sun light is its irradiance in W/m^2
    bl_light.energy = strength
    # Mitsuba directional emitters are delta lights
    bl_light.angle = 0.0

    if 'to_world' in mi_props:
        matrix = mi_transform_to_bl_transform(mi_props.get('to_world'))
    elif 'direction' in mi_props:
        matrix = _direction_matrix(
            Vector(list(mi_props.get('direction'))), Vector([0.0, 1.0, 0.0]))
    else:
        matrix = Matrix()
    return bl_light, mi_context.mi_space_to_bl_space(matrix @ _FLIP)


_converters = {
    'point': _convert_point,
    'spot': _convert_spot,
    'directional': _convert_directional,
}


######################
##  Area emitters   ##
######################

_area_shapes = ('rectangle', 'disk', 'sphere')


def can_convert_area_emitter(mi_shape_props):
    '''Whether a shape carrying an area emitter can become a Blender
    light instead of an emissive mesh.'''
    return mi_shape_props.plugin_name() in _area_shapes


def is_placeholder_bsdf(mi_bsdf_props):
    '''Whether a BSDF only exists to satisfy Mitsuba, which requires one on
    every shape. The exporter gives emitter-only materials and Blender
    lights the black diffuse BSDF shared as "empty-emitter-bsdf"; such a
    shape is a light source, not an emissive surface.'''
    from mitsuba import Properties
    plugin_name = mi_bsdf_props.plugin_name()
    if plugin_name == 'null':
        return True
    if plugin_name != 'diffuse' or 'reflectance' not in mi_bsdf_props:
        return False
    prop_type = mi_bsdf_props.type('reflectance')
    if prop_type == Properties.Type.Color:
        return max(list(mi_bsdf_props['reflectance'])) == 0.0
    if prop_type == Properties.Type.Float:
        return float(mi_bsdf_props['reflectance']) == 0.0
    return False


def mi_area_emitter_to_bl_light(mi_context, mi_emitter, mi_shape):
    '''Convert an area emitter attached to a rectangle, disk or sphere
    shape into a Blender area or point light. Returns (bl_light,
    world_matrix), or None (with a warning) on failure.'''
    try:
        shape_type = mi_shape.plugin_name()
        if shape_type not in _area_shapes:
            raise ValueError(f'shape type "{shape_type}" cannot be '
                             'converted to a Blender light')
        color, radiance = mi_spectra_utils.convert_radiance_property(
            mi_context, mi_emitter, 'radiance', [1.0, 1.0, 1.0])
        matrix = mi_context.mi_space_to_bl_space(
            mi_transform_to_bl_transform(mi_shape.get('to_world', None)))
        name = _light_name(mi_emitter)

        if shape_type == 'sphere':
            # Blender represents sphere emitters as point lights with a
            # radius
            scale = matrix.to_scale()
            radius = float(mi_shape.get('radius', 1.0)) \
                * (abs(scale.x) + abs(scale.y) + abs(scale.z)) / 3.0
            if 'center' in mi_shape:
                center = Vector(list(mi_shape.get('center')))
                matrix = matrix @ Matrix.Translation(center)
            bl_light = bpy.data.lights.new(name=name, type='POINT')
            bl_light.shadow_soft_size = radius
            bl_light.color = color
            bl_light.energy = radiance_to_power(radiance, sphere_area(radius))
            return bl_light, Matrix.Translation(matrix.to_translation())

        # Mitsuba rectangles and disks span [-1, 1] locally; the world
        # scale carries the actual dimensions
        scale = matrix.to_scale()
        sx, sy = abs(scale.x), abs(scale.y)
        bl_light = bpy.data.lights.new(name=name, type='AREA')
        if shape_type == 'rectangle':
            bl_light.shape = 'RECTANGLE'
            bl_light.size = 2.0
            bl_light.size_y = 2.0
            area = (2.0 * sx) * (2.0 * sy)
        else:
            if math.isclose(sx, sy, rel_tol=1e-5):
                bl_light.shape = 'DISK'
                bl_light.size = 2.0
            else:
                bl_light.shape = 'ELLIPSE'
                bl_light.size = 2.0
                bl_light.size_y = 2.0
            area = math.pi * sx * sy
        bl_light.color = color
        bl_light.energy = radiance_to_power(radiance, area)
        # Blender area lights emit along -Z, Mitsuba shapes along +Z
        # unless their normals are flipped
        if not mi_shape.get('flip_normals', False):
            matrix = matrix @ _FLIP
        return bl_light, matrix
    except Exception as e:
        mi_context.log(f'Failed to convert area emitter '
                       f'"{mi_emitter.id() or mi_emitter.plugin_name()}": '
                       f'{e}.', 'WARN')
        return None


######################
##   Main import    ##
######################

def mi_emitter_to_bl_light(mi_context, mi_props):
    '''Convert a Mitsuba emitter into a Blender light. Returns (bl_light,
    world_matrix), or None (with a warning) when the emitter is not
    supported or fails to convert.'''
    emitter_type = mi_props.plugin_name()
    converter = _converters.get(emitter_type)
    if converter is None:
        mi_context.log(f'Mitsuba emitter type "{emitter_type}" is not '
                       'supported.', 'WARN')
        return None
    try:
        return converter(mi_context, mi_props)
    except Exception as e:
        mi_context.log(f'Failed to convert emitter '
                       f'"{mi_props.id() or emitter_type}": {e}.', 'WARN')
        return None
