from mathutils import Matrix
import numpy as np
from .file_api import Files

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

    #export transform as a combination of rotations and translation
    params['to_world'] = export_ctx.camera_transform(b_camera)

    sampler = {'plugin':'sampler'}
    sampler['type'] = 'independent'
    sampler['sample_count'] = {
        'type': 'integer',
        'value': '$spp' # CLI set or default tag
    }
    params['sampler'] = sampler

    film = {'plugin':'film'}
    film['type'] = 'hdrfilm'
    film['width'] = {
        'type': 'integer',
        'value': '$resx' # CLI set or default tag
    }
    film['height'] = {
        'type': 'integer',
        'value': '$resy' # CLI set or default tag
    }
    params['film'] = film
    # if 'default' tags are not set, set them
    if not export_ctx.data_get('spp'):

        default_spp = {
                'type': 'default',
                'name': 'spp',
                'value': b_scene.cycles.samples
            }
        export_ctx.data_add(default_spp, name='spp', file=Files.CAMS)

        scale = C.scene.render.resolution_percentage / 100
        width = int(C.scene.render.resolution_x * scale)
        height = int(C.scene.render.resolution_y * scale)
        default_resx = {
                'type': 'default',
                'name': 'resx',
                'value': width
            }
        export_ctx.data_add(default_resx, name='resx', file=Files.CAMS)
        default_resy = {
                'type': 'default',
                'name': 'resy',
                'value': height
            }
        export_ctx.data_add(default_resy, name='resy', file=Files.CAMS)

    #TODO: reconstruction filter
    export_ctx.data_add(params, file=Files.CAMS)
