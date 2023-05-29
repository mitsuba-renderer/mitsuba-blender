from mathutils import Matrix
import numpy as np
from math import degrees


def export_camera(camera_instance, b_scene, export_ctx):
    #camera
    b_camera = camera_instance.object#TODO: instances here too?
    params = {}
    params['type'] = 'perspective'

    res_x = b_scene.render.resolution_x
    res_y = b_scene.render.resolution_y

    # Extract fov
    sensor_fit = b_camera.data.sensor_fit
    if sensor_fit == 'AUTO':
        params['fov_axis'] = 'x' if res_x >= res_y else 'y'
        params['fov'] = degrees(b_camera.data.angle_x)
    elif sensor_fit == 'HORIZONTAL':
        params['fov_axis'] = 'x'
        params['fov'] = degrees(b_camera.data.angle_x)
    elif sensor_fit == 'VERTICAL':
        params['fov_axis'] = 'y'
        params['fov'] = degrees(b_camera.data.angle_y)
    else:
        export_ctx.log(f'Unknown \'sensor_fit\' value when exporting camera: {sensor_fit}', 'ERROR')

    params["principal_point_offset_x"] = b_camera.data.shift_x / res_x * max(res_x, res_y)
    params["principal_point_offset_y"] = -b_camera.data.shift_y / res_y * max(res_x, res_y)

    #TODO: test other parameters relevance (camera.lens, orthographic_scale, dof...)
    params['near_clip'] = b_camera.data.clip_start
    params['far_clip'] = b_camera.data.clip_end
    #TODO: check that distance units are consistent everywhere (e.g. mm everywhere)
    #TODO enable focus thin lens / cam.dof

    init_rot = Matrix.Rotation(np.pi, 4, 'Y')
    params['to_world'] = export_ctx.transform_matrix(b_camera.matrix_world @ init_rot)

    if b_scene.render.engine == 'MITSUBA':
        sampler = getattr(b_camera.data.mitsuba.samplers, b_camera.data.mitsuba.active_sampler).to_dict()
    else:
        sampler = {'type' : 'independent'}
        sampler['sample_count'] = b_scene.cycles.samples

    params['sampler'] = sampler

    film = {}
    film['type'] = 'hdrfilm'

    scale = b_scene.render.resolution_percentage / 100
    film['width'] = int(res_x * scale)
    film['height'] = int(res_y * scale)


    if b_scene.render.engine == 'MITSUBA':
        film['rfilter'] = getattr(b_camera.data.mitsuba.rfilters, b_camera.data.mitsuba.active_rfilter).to_dict()
    elif b_scene.render.engine == 'CYCLES':
        if b_scene.cycles.pixel_filter_type == 'GAUSSIAN':
            film['rfilter'] = {
                'type': 'gaussian',
                'stddev' : b_scene.cycles.filter_width
            }
        elif b_scene.cycles.pixel_filter_type == 'BOX':
            film['rfilter'] = {'type' : 'box'}
        elif b_scene.cycles.pixel_filter_type == 'BLACKMAN_HARRIS':
            export_ctx.log("BLACKMAN_HARRIS filter is not supported by Mitsuba!", 'WARN')

    params['film'] = film

    if export_ctx.export_ids:
        export_ctx.data_add(params, name=b_camera.name_full)
    else:
        export_ctx.data_add(params)
