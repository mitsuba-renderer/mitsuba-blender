from .. import logging
from mathutils import Matrix
import numpy as np

def convert_area_light(b_light, ctx):
    params = {}

    # Mitsuba default disks and rectangles are twice as big as blender's
    scale_mat = Matrix.Scale(0.5, 4)
    # Mitsuba default disks and rectangles face up and blender's face down
    params['flip_normals'] = True

    # Compute area and scale
    if b_light.data.shape == 'SQUARE':
        params['type'] = 'rectangle'
        scale_mat = Matrix.Scale(b_light.data.size, 4) @ scale_mat
        x = b_light.data.size * b_light.scale.x
        y = b_light.data.size * b_light.scale.y
        area = x*y

    elif b_light.data.shape == 'RECTANGLE':
        params['type'] = 'rectangle'
        scale = Matrix()
        scale[0][0] = b_light.data.size
        scale[1][1] = b_light.data.size_y
        scale_mat = scale @ scale_mat
        x = b_light.data.size * b_light.scale.x
        y = b_light.data.size_y * b_light.scale.y
        area = x*y

    elif b_light.data.shape == 'DISK':
        params['type'] = 'disk'
        scale_mat = Matrix.Scale(b_light.data.size, 4) @ scale_mat
        # size is the diameter
        diam_x = b_light.data.size * b_light.scale.x
        diam_y = b_light.data.size * b_light.scale.y
        area = (np.pi * 0.25 * diam_x * diam_y)
    else:
        raise NotImplementedError("Light shape: %s is not supported." % b_light.data.shape)

    # Object transform
    params['to_world'] = ctx.transform_matrix(b_light.matrix_world @ scale_mat)
    emitter = {
        'type': 'area'
    }
    # Conversion factor used in Cycles, to convert to irradiance (don't ask me why)
    conv_fac = 1.0 / (area * 4.0)
    emitter['radiance'] = ctx.spectrum(conv_fac * b_light.data.energy * b_light.data.color)
    params['emitter'] = emitter

    # Adding a null bsdf
    params['bsdf'] = { 'type': 'null' }
    return params

def convert_point_light(b_light, ctx):
    # Get the world position. b_light.location is only local
    to_world = ctx.transform_matrix(b_light.matrix_world)
    position = list(to_world.translation())
    radius = b_light.data.shadow_soft_size

    # Normalize by the solid angle of a sphere
    energy = b_light.data.energy / (4 * np.pi)
    intensity = ctx.spectrum(energy * b_light.data.color)

    if radius > 1e-3:
        return {
            'type': 'spherelight',
            'position': position,
            'radius': radius,
            'intensity': intensity,
            'soft_falloff': b_light.data.use_soft_falloff
        }
    else:
        return {
            'type'      : 'point',
            'position'  : position,
            'intensity' : intensity
        }

def convert_sun_light(b_light, ctx):
    params = {
        'type': 'directional'
    }
    irradiance = b_light.data.energy * b_light.data.color
    params['irradiance'] = ctx.spectrum(irradiance)
    init_mat = Matrix.Rotation(np.pi, 4, 'X')
    # Change default position, apply transform and change coordinates
    params['to_world'] = ctx.transform_matrix(b_light.matrix_world @ init_mat)
    return params

def convert_spot_light(b_light, ctx):
    params = {
        'type': 'spot'
    }
    if b_light.data.shadow_soft_size:
        logging.warn("Light '%s' has a non-zero soft shadow radius. It will be ignored." % b_light.name_full)
    intensity = b_light.data.energy * b_light.data.color / (4.0 * np.pi)
    params['intensity'] = ctx.spectrum(intensity)
    alpha = b_light.data.spot_size / 2.0
    params['cutoff_angle'] = alpha * 180 / np.pi
    b = b_light.data.spot_blend
    # Interior angle, computed according to this code : https://developer.blender.org/diffusion/B/browse/master/intern/cycles/kernel/kernel_light.h$149
    params['beam_width'] = np.degrees(np.arccos(b + (1.0-b) * np.cos(alpha)))
    init_mat = Matrix.Rotation(np.pi, 4, 'X')
    # Change default position, apply transform and change coordinates
    params['to_world'] = ctx.transform_matrix(b_light.matrix_world @ init_mat)
    #TODO: look_at
    return params

light_converters = {
    'AREA':  convert_area_light,
    'POINT': convert_point_light,
    'SUN':   convert_sun_light,
    'SPOT':  convert_spot_light
}

def export_light(ctx, light_instance):
    b_light = light_instance.object
    try:
        params = light_converters[b_light.data.type](b_light, ctx)
        ctx.add_object(b_light.name_full, params, "emit-%s" % b_light.name_full)
    except KeyError:
        logging.warn("Could not export '%s', light type %s is not supported" % (b_light.name_full, b_light.data.type))
    except NotImplementedError as err:
        logging.warn("Error while exporting light: '%s': %s" % (b_light.name_full, err.args[0]))
