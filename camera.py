from mathutils import Matrix
import numpy as np
from .file_api import Files

def export_camera(C, camera_instance, b_scene, export_ctx):
    #camera
    b_camera = camera_instance.object#TODO: instances here too?
    params = {}
    params['type'] = 'perspective'
    #extract fov
    params['fov_axis'] = 'x'
    params['fov'] = b_camera.data.angle_x * 180 / np.pi#TODO: check cam.sensor_fit

    #TODO: test other parameters relevance (camera.lens, orthographic_scale, dof...)
    params['near_clip'] = b_camera.data.clip_start
    params['far_clip'] = b_camera.data.clip_end
    #TODO: check that distance units are consistent everywhere (e.g. mm everywhere)
    #TODO enable focus thin lens / cam.dof

    init_rot = Matrix.Rotation(np.pi, 4, 'Y')
    params['to_world'] = export_ctx.transform_matrix(b_camera.matrix_world @ init_rot)

    sampler = {}
    sampler['type'] = 'independent'
    sampler['sample_count'] = b_scene.cycles.samples

    params['sampler'] = sampler

    film = {}
    film['type'] = 'hdrfilm'

    scale = C.scene.render.resolution_percentage / 100
    film['width'] = int(C.scene.render.resolution_x * scale)
    film['height'] = int(C.scene.render.resolution_y * scale)

    params['film'] = film

    #TODO: reconstruction filter
    export_ctx.data_add(params)
