from mathutils import Matrix, Euler
import math
import numpy as np
from .export_context import Files
import bpy

def export_camera(camera_instance, b_scene, export_ctx):
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

    if b_scene.render.engine == 'MITSUBA2':
        sampler = getattr(b_camera.data.mitsuba.samplers, b_camera.data.mitsuba.active_sampler).to_dict()
    else:
        sampler = {'type' : 'independent'}
        sampler['sample_count'] = b_scene.cycles.samples

    params['sampler'] = sampler

    film = {}
    film['type'] = 'hdrfilm'

    scale = b_scene.render.resolution_percentage / 100
    film['width'] = int(b_scene.render.resolution_x * scale)
    film['height'] = int(b_scene.render.resolution_y * scale)


    if b_scene.render.engine == 'MITSUBA2':
        film['rfilter'] = getattr(b_camera.data.mitsuba.rfilters, b_camera.data.mitsuba.active_rfilter).to_dict()
    elif b_scene.render.engine == 'CYCLES':
        if b_scene.cycles.pixel_filter_type == 'GAUSSIAN':
            film['rfilter'] = {
                'type': 'gaussian',
                'stddev' : b_scene.cycles.filter_width
            }
        elif b_scene.cycles.pixel_filter_type == 'BOX':
            film['rfilter'] = {'type' : 'box'}

    params['film'] = film

    if export_ctx.export_ids:
        export_ctx.data_add(params, name=b_camera.name_full)
    else:
        export_ctx.data_add(params)

def _import_sampler(axis_mat, collection, mi_sampler, scene_props, b_camera):
    sampler_type = mi_sampler.plugin_name()

    mi_sampler_props = None
    if bpy.context.scene.render.engine == 'MITSUBA2':
        mi_sampler_props = getattr(b_camera.data.mitsuba.samplers, sampler_type, None)
        if mi_sampler_props:
            b_camera.data.mitsuba.active_sampler = sampler_type
        else:
            raise NotImplementedError(f'Sampler "{sampler_type}" not implemented.')

    for prop_name in mi_sampler.property_names():
        if prop_name == 'sample_count':
            if bpy.context.scene.render.engine == 'MITSUBA2':
                mi_sampler_props.sample_count = mi_sampler['sample_count']
            elif bpy.context.scene.render.engine == 'CYCLES':
                bpy.context.scene.cycles.samples = mi_sampler['sample_count']
        elif prop_name == 'seed':
            if bpy.context.scene.render.engine == 'MITSUBA2':
                mi_sampler_props.seed = mi_sampler['seed']
            elif bpy.context.scene.render.engine == 'CYCLES':
                bpy.context.scene.cycles.seed = mi_sampler['seed']
        else:
            raise NotImplementedError(f'Sampler property "{prop_name}" not implemented.')

def _import_rfilter(axis_mat, collection, mi_filter, scene_props, b_camera):
    filter_type = mi_filter.plugin_name()

    mi_rfilter_props = None
    if bpy.context.scene.render.engine == 'MITSUBA2':
        mi_rfilter_props = getattr(b_camera.data.mitsuba.rfilters, filter_type, None)
        if mi_rfilter_props:
            b_camera.data.mitsuba.active_rfilter = filter_type
        else:
            raise NotImplementedError(f'Reconstruction filter "{filter_type}" not implemented.')
    elif bpy.context.scene.render.engine == 'CYCLES':
        if filter_type == 'box':
            bpy.context.scene.cycles.pixel_filter_type = 'BOX'
        elif filter_type == 'gaussian':
            bpy.context.scene.cycles.pixel_filter_type = 'GAUSSIAN'
        else:
            bpy.context.scene.cycles.pixel_filter_type = 'BOX'

    for prop_name in mi_filter.property_names():
        if prop_name == 'stddev':
            if bpy.context.scene.render.engine == 'MITSUBA2':
                mi_rfilter_props.stddev = mi_filter['stddev']
            elif bpy.context.scene.render.engine == 'CYCLES':
                bpy.context.scene.cycles.filter_width = mi_filter['stddev']
        elif prop_name == 'B':
            if bpy.context.scene.render.engine == 'MITSUBA2':
                mi_rfilter_props.B = mi_filter['B']
        elif prop_name == 'C':
            if bpy.context.scene.render.engine == 'MITSUBA2':
                mi_rfilter_props.C = mi_filter['C']
        elif prop_name == 'lobes':
            if bpy.context.scene.render.engine == 'MITSUBA2':
                mi_rfilter_props.lobes = mi_filter['lobes']
        else:
            raise NotImplementedError(f'Reconstruction filter property "{prop_name}" not implemented.')

def _import_film(axis_mat, collection, mi_film, scene_props, b_camera):
    film_type = mi_film.plugin_name()
    for prop_name in mi_film.property_names():
        if prop_name == 'width':
            bpy.context.scene.render.resolution_percentage = 100
            bpy.context.scene.render.resolution_x = mi_film['width']
        elif prop_name == 'height':
            bpy.context.scene.render.resolution_percentage = 100
            bpy.context.scene.render.resolution_y = mi_film['height']
        elif mi_film.type(prop_name) == mi_film.Type.String and mi_film[prop_name] in scene_props:
            class_, prop = scene_props[mi_film[prop_name]]
            if class_ == 'ReconstructionFilter':
                _import_rfilter(axis_mat, collection, prop, scene_props, b_camera)
            else:
                raise NotImplementedError(f'Film object "{class_}" not implemented.')
        else:
            raise NotImplementedError(f'Film property "{prop_name}" not implemented.')


def import_camera(axis_mat, collection, mi_camera, scene_props):
    camera_type = mi_camera.plugin_name()    

    camera_data = bpy.data.cameras.new(name='Camera')
    camera_object = bpy.data.objects.new('Camera', camera_data)
    bpy.context.scene.camera = camera_object

    if camera_type == 'perspective':
        camera_data.type = 'PERSP'
    else:
        raise NotImplementedError(f'Sensor type "{camera_type}" not implemented.')

    inv_axis_mat = axis_mat.inverted()
    camera_transform = Matrix()
    for prop_name in mi_camera.property_names():
        if prop_name == 'fov':
            angle_axis = mi_camera.get('fov_axis', 'x')
            if angle_axis == 'y':
                camera_data.angle_y = math.radians(mi_camera['fov'])
            else:
                camera_data.angle_x = math.radians(mi_camera['fov'])
        elif prop_name == 'fov_axis':
            pass
        elif prop_name == 'near_clip':
            camera_data.clip_start = mi_camera['near_clip']
        elif prop_name == 'far_clip':
            camera_data.clip_end = mi_camera['far_clip']
        elif prop_name == 'to_world':
            transform = mi_camera['to_world']
            mat_world = Matrix(transform.matrix.numpy())
            init_rot = Matrix.Rotation(np.pi, 4, 'Y')
            camera_transform = inv_axis_mat @ mat_world @ init_rot
        elif mi_camera.type(prop_name) == mi_camera.Type.String and mi_camera[prop_name] in scene_props:
            class_, prop = scene_props[mi_camera[prop_name]]
            if class_ == 'Sampler':
                _import_sampler(axis_mat, collection, prop, scene_props, camera_object)
            elif class_ == 'Film':
                _import_film(axis_mat, collection, prop, scene_props, camera_object)
            else:
                raise NotImplementedError(f'Sensor object "{class_}" not implemented.')
        else:
            raise NotImplementedError(f'Sensor property "{prop_name}" not implemented.')

    camera_object.matrix_world = camera_transform

    collection.objects.link(camera_object)
