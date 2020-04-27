from mathutils import Matrix
import numpy as np
from .file_api import Files

def export_light(light_instance, export_ctx):
    #light
    b_light = light_instance.object#TODO instances here too
    params = {'plugin':'emitter'}
    b_type = b_light.data.type
    if b_type == 'POINT':
        params['type'] = 'point'
        #apply coordinate change to location
        params['position'] = export_ctx.point(export_ctx.axis_mat @ b_light.location)
        energy = b_light.data.energy / (4*np.pi) #normalize by the solid angle of a sphere
        intensity = energy * b_light.data.color
        params['intensity'] = export_ctx.spectrum(intensity, 'spectrum')
    elif b_type == 'SUN':
        params['type'] = 'directional'
        irradiance = b_light.data.energy * b_light.data.color
        params['irradiance'] = export_ctx.spectrum(irradiance, 'spectrum')
        init_mat = Matrix(((1,0,0,0),
                          (0,-1,0,0),
                          (0,0,-1,0),
                          (0,0,0,1)))
        #change default position, apply transform and change coordinates
        params['to_world'] = export_ctx.transform_matrix(export_ctx.axis_mat @ b_light.matrix_world @ init_mat)
    #TODO: area light
    else:
        raise NotImplementedError("Light type {} is not supported".format(b_light.data.type))

    export_ctx.data_add(params, file=Files.EMIT)