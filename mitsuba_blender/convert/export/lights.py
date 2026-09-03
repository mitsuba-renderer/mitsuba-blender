'''Blender light to Mitsuba emitter conversion.

The radiometric conversions between Blender lights (radiant power in
watts, following the Cycles conventions) and Mitsuba emitters (radiant
intensity, irradiance or radiance) live in this module; the importer in
convert.importer.lights applies their inverses.
'''

import math

from mathutils import Matrix

from .. import ConversionError


###################
##  Radiometry   ##
###################

def power_to_intensity(power):
    '''Radiant power (W) of a Blender point or spot light to radiant
    intensity (W/sr). Cycles normalizes by the full sphere regardless of
    the spot cone angle.'''
    return power / (4.0 * math.pi)


def intensity_to_power(intensity):
    return intensity * 4.0 * math.pi


def power_to_radiance(power, area):
    '''Radiant power (W) of a one-sided Lambertian area emitter to
    radiance (W/(sr*m^2)).'''
    return power / (math.pi * area)


def radiance_to_power(radiance, area):
    return radiance * math.pi * area


def sphere_area(radius):
    return 4.0 * math.pi * radius * radius


def spot_beam_width(spot_size, spot_blend):
    '''The angle at which the falloff of a Blender spot light begins,
    following the Cycles falloff curve. All angles are in radians.'''
    alpha = spot_size / 2.0
    return math.acos(spot_blend + (1.0 - spot_blend) * math.cos(alpha))


def spot_blend(spot_size, beam_width):
    '''Inverse of spot_beam_width.'''
    denom = 1.0 - math.cos(spot_size / 2.0)
    if denom < 1e-9:
        return 0.0
    blend = (math.cos(beam_width) - math.cos(spot_size / 2.0)) / denom
    return min(max(blend, 0.0), 1.0)


####################
##   Converters   ##
####################

def _colored(scalar, color):
    return [scalar * c for c in color[:3]]


def _convert_point(export_ctx, b_light, matrix_world):
    data = b_light.data
    position = list(export_ctx.transform_matrix(matrix_world).translation())
    radius = data.shadow_soft_size
    if radius > 0.0:
        # Cycles gives the light the radiance below, but samples it as a
        # disk of radius `radius` that always faces the shaded point, so it
        # illuminates as P / (4 pi (d^2 + radius^2)). A sphere emitter has
        # the same radiance and the same far-field power, but illuminates
        # as P / (4 pi d^2) whatever its radius, so it stays brighter than
        # Cycles by 1 + (radius / d)^2. No Mitsuba emitter reproduces the
        # disk falloff; the sphere at least gets the soft shadows right.
        radiance = _colored(power_to_radiance(data.energy,
                                              sphere_area(radius)),
                            data.color)
        return {
            'type': 'sphere',
            'center': position,
            'radius': radius,
            'emitter': {
                'type': 'area',
                'radiance': export_ctx.spectrum(radiance),
                'twosided' : True,
            },
            'bsdf': {
                'type': 'diffuse',
                'reflectance': export_ctx.spectrum(0.0),
            },
        }
    return {
        'type': 'point',
        'position': position,
        'intensity': export_ctx.spectrum(
            _colored(power_to_intensity(data.energy), data.color)),
    }


def _convert_spot(export_ctx, b_light, matrix_world):
    data = b_light.data
    if data.shadow_soft_size:
        # Mitsuba spot emitters are delta lights, so unlike point lights the
        # radius cannot be modelled at all: the shadows come out hard and the
        # light stays brighter than Cycles by 1 + (radius / d)^2.
        export_ctx.log(f'Light "{b_light.name_full}" has a non-zero radius. '
                       'It will be ignored: expect hard shadows and a '
                       'slightly brighter light than Cycles.', 'WARN')
    # Blender spot lights point along -Z, Mitsuba's along +Z
    flip = Matrix.Rotation(math.pi, 4, 'X')
    return {
        'type': 'spot',
        'intensity': export_ctx.spectrum(
            _colored(power_to_intensity(data.energy), data.color)),
        'cutoff_angle': math.degrees(data.spot_size / 2.0),
        'beam_width': math.degrees(
            spot_beam_width(data.spot_size, data.spot_blend)),
        'to_world': export_ctx.transform_matrix(matrix_world @ flip),
    }


def _convert_sun(export_ctx, b_light, matrix_world):
    data = b_light.data
    if data.angle > 0.0:
        export_ctx.log(f'Light "{b_light.name_full}": Mitsuba directional '
                       'emitters have no angular diameter. Ignoring the sun '
                       'angle.', 'INFO')
    # Blender sun lights shine along -Z, Mitsuba's along +Z
    flip = Matrix.Rotation(math.pi, 4, 'X')
    # Mitsuba's directional emitter does not normalize the direction it
    # reads from `to_world`, so any object scale would scale the
    # irradiance. Cycles only uses the orientation of a sun light.
    orientation = (matrix_world @ flip).to_3x3().normalized().to_4x4()
    return {
        'type': 'directional',
        # The energy of a Blender sun light is its irradiance in W/m^2
        'irradiance': export_ctx.spectrum(_colored(data.energy, data.color)),
        'to_world': export_ctx.transform_matrix(orientation),
    }


def _convert_area(export_ctx, b_light, matrix_world):
    data = b_light.data
    obj_scale = matrix_world.to_scale()
    sx, sy = abs(obj_scale.x), abs(obj_scale.y)
    size_x = data.size
    if data.shape in ('SQUARE', 'DISK'):
        size_y = data.size
    elif data.shape in ('RECTANGLE', 'ELLIPSE'):
        size_y = data.size_y
    else:
        raise ConversionError(f'area light shape {data.shape} is not '
                              'supported')
    if data.shape in ('SQUARE', 'RECTANGLE'):
        shape = 'rectangle'
        area = (size_x * sx) * (size_y * sy)
    else:
        shape = 'disk'
        # The sizes are the diameters of the ellipse
        area = math.pi / 4.0 * (size_x * sx) * (size_y * sy)
    if area == 0.0:
        raise ConversionError('the area light is degenerate')
    if data.spread < math.pi - 1e-5:
        export_ctx.log(f'Light "{b_light.name_full}" has a spread angle, '
                       'which Mitsuba does not support. Ignoring it.', 'WARN')

    # Mitsuba rectangles and disks span [-1, 1] locally
    local = Matrix.Diagonal((size_x / 2.0, size_y / 2.0, 1.0)).to_4x4()
    radiance = _colored(power_to_radiance(data.energy, area), data.color)
    return {
        'type': shape,
        # Blender area lights emit along -Z, Mitsuba shapes along +Z
        'flip_normals': True,
        'to_world': export_ctx.transform_matrix(matrix_world @ local),
        'emitter': {
            'type': 'area',
            'radiance': export_ctx.spectrum(radiance),
            'twosided' : True,
        },
        'bsdf': {
            'type': 'diffuse',
            'reflectance' : export_ctx.spectrum(0.0)
        },
    }


_converters = {
    'POINT': _convert_point,
    'SPOT': _convert_spot,
    'SUN': _convert_sun,
    'AREA': _convert_area,
}


def convert_light(export_ctx, b_light, matrix_world=None):
    '''Convert a Blender light object into a Mitsuba plugin dict.
    Raises ConversionError for unsupported lights.'''
    converter = _converters.get(b_light.data.type)
    if converter is None:
        raise ConversionError(f'light type {b_light.data.type} is not '
                              'supported')
    if matrix_world is None:
        matrix_world = b_light.matrix_world
    emitter = converter(export_ctx, b_light, matrix_world)

    if not b_light.visible_camera:
        if 'emitter' in emitter and isinstance(emitter['emitter'], dict):
            emitter['emitter']['visible'] = False
        else:
            emitter['visible'] = False
    return emitter


def export_light(export_ctx, light_instance):
    '''Convert a depsgraph light instance and add it to the scene dict.
    Never raises: failures produce a warning and the light is skipped.'''
    b_light = light_instance.object
    try:
        params = convert_light(export_ctx, b_light,
                               light_instance.matrix_world.copy())
    except Exception as e:
        export_ctx.log(f'Failed to export light "{b_light.name_full}": {e}. '
                       'Skipping it.', 'WARN')
        return
    if export_ctx.export_ids:
        export_ctx.data_add(params, name=f'emit-{b_light.name_full}')
    else:
        export_ctx.data_add(params)
