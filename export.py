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

from .file_api import FileExportContext
from .materials import export_world
from .geometry import GeometryExporter
from .lights import export_light
from .camera import export_camera

from bpy_extras.io_utils import ExportHelper

class MitsubaFileExport(bpy.types.Operator, ExportHelper):
    """Export as a Mitsuba 2 scene"""
    bl_idname = "export_scene.mitsuba2"
    bl_label = "Mitsuba 2 Export"

    filename_ext = ".xml"

    def __init__(self):
        self.reset()

    def reset(self):
        self.export_ctx = FileExportContext()
        self.geometry_exporter = GeometryExporter()

    def execute(self, context):

        self.export_ctx.set_filename(self.filepath)
        #TODO: move this
        integrator = {'plugin':'integrator', 'type':'path'}
        self.export_ctx.data_add(integrator)
        depsgraph = context.evaluated_depsgraph_get()#TODO: get RENDER evaluated depsgraph (not implemented)
        b_scene = context.scene #TODO: what if there are multiple scenes?
        export_world(self.export_ctx, b_scene.world)

        #main export loop
        for object_instance in depsgraph.object_instances:
            evaluated_obj = object_instance.object
            object_type = evaluated_obj.type
            #type: enum in [‘MESH’, ‘CURVE’, ‘SURFACE’, ‘META’, ‘FONT’, ‘ARMATURE’, ‘LATTICE’, ‘EMPTY’, ‘GPENCIL’, ‘CAMERA’, ‘LIGHT’, ‘SPEAKER’, ‘LIGHT_PROBE’], default ‘EMPTY’, (readonly)
            if evaluated_obj.hide_render:
                print("Object: {} is hidden for render. Ignoring it.".format(evaluated_obj.name))
                continue#ignore it since we don't want it rendered (TODO: hide_viewport)

            if object_type == 'MESH':
                self.geometry_exporter.export_mesh(object_instance, self.export_ctx)
            elif object_type == 'CAMERA':#TODO: export only scene.camera
                export_camera(context, object_instance, b_scene, self.export_ctx)#TODO: investigate multiple scenes and multiple cameras at same time
            elif object_type == 'LIGHT':
                export_light(object_instance, self.export_ctx)
            else:
                raise NotImplementedError("Object type {} is not supported".format(object_type))

        #write data to scene .xml file
        self.export_ctx.configure()
        #reset the exporter
        self.reset()
        return {'FINISHED'}
