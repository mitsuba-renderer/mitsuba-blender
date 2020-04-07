import xml.etree.ElementTree as ET
import bpy
from mathutils import *
import numpy as np
from os import getenv
import sys
import warnings

python_path = getenv('PYTHONPATH', 'NONE')#TODO other default value

if python_path == 'NONE':
    raise ImportError("Environment variable PYTHONPATH not set.")

tokens = python_path.split(':')
for token in tokens: #add the paths to python path
    sys.path.append(token)

sys.path.append('/home/bathal/Documents/EPFL/mitsuba-blender/')#ugly workaround, TODO resolve paths properly
from file_api import FileExportContext
from materials import export_material, export_world
from geometry import GeometryExporter

C = bpy.context
D = bpy.data

def export_camera(camera_instance, b_scene, export_ctx):
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

def export_light(light_instance, export_ctx):
    #light
    b_light = light_instance.object#TODO instances here too
    params = {'plugin':'emitter'}
    b_type = b_light.data.type
    if b_type == 'POINT':
        params['type'] = 'point'
        params['position'] = export_ctx.point(b_light.location)
        params['intensity'] = export_ctx.spectrum(b_light.data.energy/(4*np.pi), 'spectrum')
    elif b_type == 'SUN':
        params['type'] = 'directional'
        color = b_light.data.color
        irradiance = b_light.data.energy * color
        params['irradiance'] = export_ctx.spectrum(irradiance)
        init_mat = Matrix(((1,0,0,0),
                          (0,-1,0,0),
                          (0,0,-1,0),
                          (0,0,0,1)))
        params['to_world'] = export_ctx.transform_matrix(b_light.matrix_world @ init_mat)
    #TODO: area light
    else:
        raise NotImplementedError("Light type {} is not supported".format(b_light.data.type))

    export_ctx.data_add(params)

export_ctx = FileExportContext()
geometry_exporter = GeometryExporter()
path = "/home/bathal/Documents/EPFL/scenes/Test/Test.xml"
export_ctx.set_filename(path)
integrator = {'plugin':'integrator', 'type':'path'}
export_ctx.data_add(integrator)

depsgraph = C.evaluated_depsgraph_get()#TODO: get RENDER evaluated depsgraph (not implemented)
b_scene = D.scenes[0] #TODO: what if there are multiple scenes?
#main export loop
export_world(export_ctx, b_scene.world)

#TODO: also export images only once with refs
for b_mat in D.materials:
    #export materials
    if b_mat.users > 0:#if the material is used
        export_material(export_ctx, b_mat)

for object_instance in depsgraph.object_instances:
    evaluated_obj = object_instance.object
    object_type = evaluated_obj.type
    #type: enum in [‘MESH’, ‘CURVE’, ‘SURFACE’, ‘META’, ‘FONT’, ‘ARMATURE’, ‘LATTICE’, ‘EMPTY’, ‘GPENCIL’, ‘CAMERA’, ‘LIGHT’, ‘SPEAKER’, ‘LIGHT_PROBE’], default ‘EMPTY’, (readonly)
    if evaluated_obj.hide_render:
        print("Object: {} is hidden for render. Ignoring it.".format(evaluated_obj.name))
        continue#ignore it since we don't want it rendered (TODO: hide_viewport)

    if object_type == 'MESH':
        geometry_exporter.export_mesh(object_instance, export_ctx)
    elif object_type == 'CAMERA':#TODO: export only scene.camera
        export_camera(object_instance, b_scene, export_ctx)#TODO: investigate multiple scenes and multiple cameras at same time
    elif object_type == 'LIGHT':
        export_light(object_instance, export_ctx)
    else:
        raise NotImplementedError("Object type {} is not supported".format(object_type))

#write data to scene .xml file
export_ctx.configure()
