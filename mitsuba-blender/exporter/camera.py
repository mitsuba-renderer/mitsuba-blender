import os
from mathutils import Matrix
import numpy as np
from math import degrees

from .. import logging

def export_camera(ctx, camera_instance, b_scene):
    '''
    Export a Mitsuba camera from a Blender camera
    '''
    import drjit as dr
    b_camera = camera_instance.object # TODO: instances here too?

    res_x = b_scene.render.resolution_x
    res_y = b_scene.render.resolution_y

    params = {}

    if b_camera.data.type == 'PERSP':

        # Extract fov
        sensor_fit = b_camera.data.sensor_fit
        if sensor_fit == 'AUTO':
            fov_axis = 'x' if res_x >= res_y else 'y'
            fov = degrees(b_camera.data.angle_x)
        elif sensor_fit == 'HORIZONTAL':
            fov_axis = 'x'
            fov = degrees(b_camera.data.angle_x)
        elif sensor_fit == 'VERTICAL':
            fov_axis = 'y'
            fov = degrees(b_camera.data.angle_y)
        else:
            logging.error(f'Unknown \'sensor_fit\' value when exporting camera: {sensor_fit}')

        principal_point_offset_x =  b_camera.data.shift_x / res_x * max(res_x, res_y)
        principal_point_offset_y = -b_camera.data.shift_y / res_y * max(res_x, res_y)

        #TODO: check that distance units are consistent everywhere (e.g. mm everywhere)
        #TODO enable focus thin lens / cam.dof

        init_rot = Matrix.Rotation(np.pi, 4, 'Y')
        to_world = ctx.transform_matrix(b_camera.matrix_world @ init_rot)

        params = {
            'type': 'perspective',
            'fov_axis': fov_axis,
            'fov': fov,
            'principal_point_offset_x': principal_point_offset_x,
            'principal_point_offset_y': principal_point_offset_y,
            'near_clip': b_camera.data.clip_start,
            'far_clip': b_camera.data.clip_end,
            'to_world': to_world,
        }
    elif b_camera.data.type == 'ORTHO':
        init_rot = Matrix.Rotation(np.pi, 4, 'Y')
        scale = b_camera.data.ortho_scale / 2.0
        to_world = b_camera.matrix_world @ init_rot @ Matrix.Diagonal([scale, scale, scale, 1])
        to_world = ctx.transform_matrix(to_world)
        params = {
            'type': 'orthographic',
            'to_world': to_world,
            'near_clip': 0.001,                        # TODO check this
            'far_clip':  2.5 * b_camera.data.clip_end, # TODO check this
        }

    if b_scene.render.engine == 'Mitsuba':
        sampler = getattr(b_camera.data.mitsuba_engine.samplers, b_camera.data.mitsuba_engine.active_sampler).to_dict()
    else:
        sampler = { 'type' : 'independent' }
        sampler['sample_count'] = b_scene.cycles.samples

    params['sampler'] = sampler

    film = {}
    film['type'] = 'hdrfilm'

    scale = b_scene.render.resolution_percentage / 100
    film['width']  = int(res_x * scale)
    film['height'] = int(res_y * scale)
    film['pixel_format'] = 'rgb'

    if b_scene.render.engine == 'Mitsuba':
        film['rfilter'] = getattr(b_camera.data.mitsuba_engine.rfilters, b_camera.data.mitsuba_engine.active_rfilter).to_dict()
    elif b_scene.render.engine == 'CYCLES':
        if b_scene.cycles.pixel_filter_type == 'GAUSSIAN':
            film['rfilter'] = {
                'type': 'gaussian',
                'stddev' : b_scene.cycles.filter_width
            }
        elif b_scene.cycles.pixel_filter_type == 'BOX':
            film['rfilter'] = {'type' : 'box'}
        elif b_scene.cycles.pixel_filter_type == 'BLACKMAN_HARRIS':
            logging.warn("BLACKMAN_HARRIS filter is not supported by Mitsuba!")

    params['film'] = film

    ctx.add_object(b_camera.name_full, params, b_camera.name_full)
