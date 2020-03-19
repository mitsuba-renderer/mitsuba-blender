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

import mitsuba
mitsuba.set_variant('scalar_rgb')
from mitsuba.render import Mesh
from mitsuba.core import FileStream, Matrix4f

C = bpy.context
D = bpy.data
depsgraph = C.evaluated_depsgraph_get()
b_scene = D.scenes[0] #TODO: what if there are multiple scenes?
path = "/home/bathal/Documents/EPFL/scenes/Test/"

#TODO: write xml writing code elsewhere
def add_string(parent, n, v):
    ET.SubElement(parent, "string", name=n, value=v)

def add_int(parent, n, v):
    ET.SubElement(parent, "integer", name=n, value=str(v))
    
def add_float(parent, n, v):
    ET.SubElement(parent, "float", name=n, value=str(v))

def add_matrix(parent, m, n, mat):
    """
    parent: parent node in the XML structure
    m,n: matrix dimensions
    mat: matrix
    """
    str_mat = ""
    for i in range(m):
        for j in range(n):
            str_mat += " " + str(mat[i][j])
    ET.SubElement(parent, "matrix", value=str_mat)

def add_rgb(parent, n, vec):
    ET.SubElement(parent, "rgb", name=n, value="{}, {}, {}".format(*vec))

#coordinate system change between blender and mitsuba
coordinate_mat = Matrix(((-1,0,0,0),(0,1,0,0),(0,0,-1,0),(0,0,0,1)))

scene = ET.Element("scene", version="2.0.0")

integrator = ET.SubElement(scene, "integrator", type="path")#debug
#TODO: add path tracer params

def export_camera(b_camera):
    #camera
    sensor = ET.SubElement(scene, "sensor", type="perspective")#TODO: handle other types (thin lens, ortho)

    #TODO: encapsulating classes for everything
    #extract fov
    add_string(sensor, "fov_axis", "x")#TODO: check cam.sensor_fit
    add_float(sensor, "fov", str(b_camera.data.angle_x * 180 / np.pi))
    #TODO: test other parameters relevance (camera.lens, orthographic_scale, dof...)
    add_float(sensor, "near_clip", str(b_camera.data.clip_start))
    add_float(sensor, "far_clip", str(b_camera.data.clip_end))
    #TODO: check that distance units are consistent everywhere (e.g. mm everywhere)
    #TODO enable focus thin lens / cam.dof

    transform = ET.SubElement(sensor, "transform", name="to_world")

    add_matrix(transform, 4, 4, b_camera.matrix_world @ coordinate_mat) #TODO: constraints, anim data,etc. (deg evaluation)

    sampler = ET.SubElement(sensor, "sampler", type="independent")
    add_int(sampler, "sample_count", b_scene.cycles.preview_samples)#debug, TODO: switch to samples

    film = ET.SubElement(sensor, "film", type="hdrfilm")
    scale = C.scene.render.resolution_percentage / 100
    width = int(C.scene.render.resolution_x * scale)
    add_int(film, "width", width)
    height = int(C.scene.render.resolution_y * scale)
    add_int(film, "height", height)
    #TODO: reconstruction filter

def export_mesh(b_mesh):
    #object export

    #create a mitsuba mesh
    b_mesh.data.calc_loop_triangles()#compute the triangle tesselation
    loop_tri_count = len(b_mesh.data.loop_triangles)
    name = b_mesh.name #or name_full? TODO: check when those are different
    if loop_tri_count == 0:
        warnings.warn("Mesh: {} has no faces. Skipping.".format(name), Warning)
        return

    loop_tri_ptr = b_mesh.data.loop_triangles[0].as_pointer()
    loop_ptr = b_mesh.data.loops[0].as_pointer()
    poly_ptr = b_mesh.data.polygons[0].as_pointer()
    vert_ptr = b_mesh.data.vertices[0].as_pointer()
    mat = b_mesh.matrix_world
    to_world = Matrix4f(mat[0][0], mat[0][1], mat[0][2], mat[0][3],
                        mat[1][0], mat[1][1], mat[1][2], mat[1][3],
                        mat[2][0], mat[2][1], mat[2][2], mat[2][3],
                        mat[3][0], mat[3][1], mat[3][2], mat[3][3])
    m_mesh = Mesh(name, loop_tri_count, loop_tri_ptr, loop_ptr, vert_ptr, poly_ptr, to_world)

    mesh_path = path + "/" + name + ".ply"
    shape = ET.SubElement(scene, "shape", type="ply")
    add_string(shape, "filename", mesh_path)
    mesh_fs = FileStream(mesh_path, FileStream.ETruncReadWrite)
    m_mesh.write_ply(mesh_fs)#save as binary ply
    mesh_fs.close()
    #TODO: this only exports the mesh as seen in the viewport, not as should be rendered
    #TODO: evaluated versions and instances
    #object texture: dummy material for now
    material = ET.SubElement(shape, "bsdf", type="diffuse")
    add_rgb(material, "reflectance", Vector((1,1,1)))

def export_light(b_light):
    #light
    if(b_light.data.type == 'POINT'):
        emitter = ET.SubElement(scene, "emitter", type="point")#TODO: handle other types
        ET.SubElement(emitter, "point", name="position", x=str(b_light.location[0]), y=str(b_light.location[1]), z=str(b_light.location[2]))
        ET.SubElement(emitter, "spectrum", name="intensity", value=str(b_light.data.energy/(4*np.pi)))#energy converted to emitted radiance (homogeneous over the sphere)
    else:
        raise NotImplementedError("Light type {} is not supported".format(b_light.data.type))

depsgraph = C.evaluated_depsgraph_get()#TODO: get RENDER evaluated depsgraph (not implemented)
#main export loop
for b_object in D.objects:
    evaluated_obj = b_object.evaluated_get(depsgraph)
    #type: enum in [‘MESH’, ‘CURVE’, ‘SURFACE’, ‘META’, ‘FONT’, ‘ARMATURE’, ‘LATTICE’, ‘EMPTY’, ‘GPENCIL’, ‘CAMERA’, ‘LIGHT’, ‘SPEAKER’, ‘LIGHT_PROBE’], default ‘EMPTY’, (readonly)
    if b_object.type == 'MESH':
        export_mesh(evaluated_obj)
    elif b_object.type == 'CAMERA':
        export_camera(evaluated_obj)#TODO: investigate multiple scenes and multiple cameras at same time
    elif b_object.type == 'LIGHT':
        export_light(evaluated_obj)
    else:
        raise NotImplementedError("Object type {} is not supported".format(b_object.type))

#write XML file
tree = ET.ElementTree(scene)
tree.write(path + "Test.xml")
