import xml.etree.ElementTree as ET
import bpy
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
from materials import export_world
from geometry import GeometryExporter
from lights import export_light
from camera import export_camera

C = bpy.context
D = bpy.data

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
        export_camera(C, object_instance, b_scene, export_ctx)#TODO: investigate multiple scenes and multiple cameras at same time
    elif object_type == 'LIGHT':
        export_light(object_instance, export_ctx)
    else:
        raise NotImplementedError("Object type {} is not supported".format(object_type))

#write data to scene .xml file
export_ctx.configure()
