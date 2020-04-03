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
from materials import export_material

import mitsuba
mitsuba.set_variant('scalar_rgb')
from mitsuba.render import Mesh
from mitsuba.core import FileStream, Matrix4f

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

def save_mesh(b_mesh, file_path):
    #create a mitsuba mesh
    b_mesh.data.calc_loop_triangles()#compute the triangle tesselation
    name = b_mesh.name_full
    loop_tri_count = len(b_mesh.data.loop_triangles)
    if loop_tri_count == 0:
        warnings.warn("Mesh: {} has no faces. Skipping.".format(name), Warning)
        return

    if not b_mesh.data.uv_layers:
        uv_ptr = 0#nullptr
    else:
        if len(b_mesh.data.uv_layers) > 1:
            print("Mesh: '%s' has multiple UV layers. Mitsuba only supports one. Exporting the one set active for render."%name)
        for uv_layer in b_mesh.data.uv_layers:
            if uv_layer.active_render:#if there is only 1 UV layer, it is always active
                uv_ptr = uv_layer.data[0].as_pointer()
                break

    if not b_mesh.data.vertex_colors:
        col_ptr = 0#nullptr
    else:
        if len(b_mesh.data.vertex_colors) > 1:
            print("Mesh: '%s' has multiple vertex color layers. Mitsuba only supports one. Exporting the one set active for render."%name)
        for color_layer in b_mesh.data.vertex_colors:
            if color_layer.active_render:#if there is only 1 UV layer, it is always active
                col_ptr = color_layer.data[0].as_pointer()
                break

    loop_tri_ptr = b_mesh.data.loop_triangles[0].as_pointer()
    loop_ptr = b_mesh.data.loops[0].as_pointer()
    poly_ptr = b_mesh.data.polygons[0].as_pointer()
    vert_ptr = b_mesh.data.vertices[0].as_pointer()
    vert_count = len(b_mesh.data.vertices)#TODO: maybe avoid calling len()
    mat = b_mesh.matrix_world
    to_world = Matrix4f(mat[0][0], mat[0][1], mat[0][2], mat[0][3],
                        mat[1][0], mat[1][1], mat[1][2], mat[1][3],
                        mat[2][0], mat[2][1], mat[2][2], mat[2][3],
                        mat[3][0], mat[3][1], mat[3][2], mat[3][3])
    m_mesh = Mesh(name, loop_tri_count, loop_tri_ptr, loop_ptr, vert_count, vert_ptr, poly_ptr, uv_ptr, col_ptr, to_world)

    mesh_fs = FileStream(file_path, FileStream.ETruncReadWrite)
    m_mesh.write_ply(mesh_fs)#save as binary ply
    mesh_fs.close()

def export_mesh(mesh_instance, export_ctx):
    #object export
    b_mesh = mesh_instance.object
    if b_mesh.is_instancer and not b_mesh.show_instancer_for_render:
        return#don't export hidden mesh

    name = b_mesh.name #or name_full? TODO: check when those are different
    mesh_path = export_ctx.directory + "/" + name + ".ply"
    if not mesh_instance.is_instance:
        save_mesh(b_mesh, mesh_path)
    if mesh_instance.is_instance or not b_mesh.parent or not b_mesh.parent.is_instancer:
        #we only write a shape plugin if an object is *not* an emitter, i.e. either an instance or an original object
        params = {'plugin':'shape', 'type':'ply'}
        params['filename'] = mesh_path
        if(mesh_instance.is_instance):
            #instance, load referenced object saved before with another transform matrix
            params['to_world'] = export_ctx.transform_matrix(mesh_instance.matrix_world @ b_mesh.matrix_world.inverted())
        #TODO: this only exports the mesh as seen in the viewport, not as should be rendered
        #object texture: dummy material for now
        #bsdf = {'plugin':'bsdf', 'type':'diffuse'}
        #bsdf['reflectance'] = export_ctx.spectrum([1,1,1], 'rgb')
        #bsdf['reflectance'] = {'plugin':'texture','name':'reflectance','type':'checkerboard'}
        if b_mesh.active_material:
            params['bsdf'] = {'type':'ref', 'id':b_mesh.active_material.name}
        else:#default bsdf
            params['bsdf'] = {'plugin':'bsdf', 'type':'diffuse'}
        #TODO: export meshes with multiple materials
        export_ctx.data_add(params)

def export_light(light_instance, export_ctx):
    #light
    b_light = light_instance.object#TODO instances here too
    params = {'plugin':'emitter'}
    if(b_light.data.type == 'POINT'):
        params['type'] = 'point'
        params['position'] = export_ctx.point(b_light.location)
        params['intensity'] = export_ctx.spectrum(b_light.data.energy/(4*np.pi), 'spectrum')
    else:
        raise NotImplementedError("Light type {} is not supported".format(b_light.data.type))

    export_ctx.data_add(params)

export_ctx = FileExportContext()
path = "/home/bathal/Documents/EPFL/scenes/Test/Test.xml"
export_ctx.set_filename(path)
integrator = {'plugin':'integrator', 'type':'path'}
export_ctx.data_add(integrator)

depsgraph = C.evaluated_depsgraph_get()#TODO: get RENDER evaluated depsgraph (not implemented)
b_scene = D.scenes[0] #TODO: what if there are multiple scenes?
#main export loop

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
        export_mesh(object_instance, export_ctx)
    elif object_type == 'CAMERA':#TODO: export only scene.camera
        export_camera(object_instance, b_scene, export_ctx)#TODO: investigate multiple scenes and multiple cameras at same time
    elif object_type == 'LIGHT':
        export_light(object_instance, export_ctx)
    else:
        raise NotImplementedError("Object type {} is not supported".format(object_type))

#write data to scene .xml file
export_ctx.configure()
