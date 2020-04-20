from mathutils import Matrix
import numpy as np

def export_camera(C, camera_instance, b_scene, export_ctx):
    #camera
    b_camera = camera_instance.object#TODO: instances here too?
    params = {'plugin':'sensor'}
    params['type'] = 'perspective'
    params['id'] = b_camera.name_full
    #TODO: encapsulating classes for everything
    #extract fov
    params['fov_axis'] = 'x'
    params['fov'] = b_camera.data.angle_x * 180 / np.pi#TODO: check cam.sensor_fit

    #TODO: test other parameters relevance (camera.lens, orthographic_scale, dof...)
    params['near_clip'] = b_camera.data.clip_start
    params['far_clip'] = b_camera.data.clip_end
    #TODO: check that distance units are consistent everywhere (e.g. mm everywhere)
    #TODO enable focus thin lens / cam.dof

    #matrix used to transform the camera, since they have different default position in blender and mitsuba (mitsuba is y up, blender is z up)
    coordinate_mat = Matrix(((-1,0,0,0),(0,1,0,0),(0,0,-1,0),(0,0,0,1)))
    params['to_world'] = export_ctx.transform_matrix(b_camera.matrix_world @ coordinate_mat)

    sampler = {'plugin':'sampler'}
    sampler['type'] = 'independent'
    sampler['sample_count'] = b_scene.cycles.samples
    params['sampler'] = sampler

    film = {'plugin':'film'}
    film['type'] = 'hdrfilm'
    scale = C.scene.render.resolution_percentage / 100
    width = int(C.scene.render.resolution_x * scale)
    film['width'] = width
    height = int(C.scene.render.resolution_y * scale)
    film['height'] = height
    params['film'] = film
    #TODO: reconstruction filter
    export_ctx.data_add(params)
