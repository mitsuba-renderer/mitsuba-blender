from mathutils import Matrix
import numpy as np
from .export_context import Files

def convert_area_light(b_light, export_ctx):
    params = {}

    # Mitsuba default disks and rectangles are twice as big as blender's
    scale_mat = Matrix.Scale(0.5, 4)
    # Mitsuba default disks and rectangles face up and blender's face down
    params['flip_normals'] = True

    #Compute area and scale
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
        if not all(x == b_light.scale.x for x in b_light.scale):
            raise NotImplementedError("Trying to export a distorted disk light. Only disks with uniform scaling are accepted.")
        x = b_light.data.size * b_light.scale.x
        area = np.pi * x**2 / 4.0 # size is the diameter
        #area = np.pi * b_light.data.size**2 / 4.0 #size is the diameter, not the radius

    else: # disks can't be non uniformly scaled in Mitsuba to create ellipses
        raise NotImplementedError("Light shape: %s is not supported." % b_light.data.shape)

    #object transform
    params['to_world'] = export_ctx.transform_matrix(b_light.matrix_world @ scale_mat)
    emitter = {
        'type': 'area'
    }
    # Conversion factor used in Cycles, to convert to irradiance (don't ask me why)
    conv_fac = 1.0 / (area * 4.0)
    emitter['radiance'] = export_ctx.spectrum(conv_fac * b_light.data.energy * b_light.data.color)
    params['emitter'] = emitter

    #adding a null bsdf
    bsdf = {
        'type': 'null'
    }
    params['bsdf'] = bsdf
    return params

def convert_point_light(b_light, export_ctx):
    params = {
        'type': 'point'
    }
    if b_light.data.shadow_soft_size:
        export_ctx.log("Light '%s' has a non-zero soft shadow radius. It will be ignored." % b_light.name_full, 'WARN')
    #apply coordinate change to location
    params['position'] = list(export_ctx.axis_mat @ b_light.location)
    energy = b_light.data.energy / (4*np.pi) #normalize by the solid angle of a sphere
    intensity = energy * b_light.data.color
    params['intensity'] = export_ctx.spectrum(intensity)
    return params

def convert_sun_light(b_light, export_ctx):
    params = {
        'type': 'directional'
    }
    irradiance = b_light.data.energy * b_light.data.color
    params['irradiance'] = export_ctx.spectrum(irradiance)
    init_mat = Matrix.Rotation(np.pi, 4, 'X')
    #change default position, apply transform and change coordinates
    params['to_world'] = export_ctx.transform_matrix(b_light.matrix_world @ init_mat)
    return params

def convert_spot_light(b_light, export_ctx):
    params = {
        'type': 'spot'
    }
    if b_light.data.shadow_soft_size:
        export_ctx.log("Light '%s' has a non-zero soft shadow radius. It will be ignored." % b_light.name_full, 'WARN')
    intensity = b_light.data.energy * b_light.data.color / (4.0 * np.pi)
    params['intensity'] = export_ctx.spectrum(intensity)
    alpha = b_light.data.spot_size / 2.0
    params['cutoff_angle'] = alpha * 180 / np.pi
    b = b_light.data.spot_blend
    # interior angle, computed according to this code : https://developer.blender.org/diffusion/B/browse/master/intern/cycles/kernel/kernel_light.h$149
    params['beam_width'] = np.degrees(np.arccos(b + (1.0-b) * np.cos(alpha)))
    init_mat = Matrix.Rotation(np.pi, 4, 'X')
    #change default position, apply transform and change coordinates
    params['to_world'] = export_ctx.transform_matrix(b_light.matrix_world @ init_mat)
    #TODO: look_at
    return params

light_converters = {
    'AREA': convert_area_light,
    'POINT': convert_point_light,
    'SUN': convert_sun_light,
    'SPOT': convert_spot_light
}

def export_light(light_instance, export_ctx):

    b_light = light_instance.object
    try:
        params = light_converters[b_light.data.type](b_light, export_ctx)
        if export_ctx.export_ids:
            export_ctx.data_add(params, name="emit-%s" % b_light.name_full)
        else:
            export_ctx.data_add(params)
    except KeyError:
        export_ctx.log("Could not export '%s', light type %s is not supported" % (b_light.name_full, b_light.data.type), 'WARN')
    except NotImplementedError as err:
        export_ctx.log("Error while exporting light: '%s': %s" % (b_light.name_full, err.args[0]), 'WARN')
