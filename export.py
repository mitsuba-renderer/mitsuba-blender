import xml.etree.ElementTree as ET
import bpy
from bpy.types import Operator, AddonPreferences
from bpy.props import StringProperty, BoolProperty
from os import getenv
import sys
import warnings

from .file_api import FileExportContext
from .materials import export_world
from .geometry import GeometryExporter
from .lights import export_light
from .camera import export_camera

from bpy_extras.io_utils import ExportHelper, axis_conversion, orientation_helper

class MitsubaPrefs(AddonPreferences):

    bl_idname = __package__

    python_path: StringProperty(
        name="Path to Mitsuba 2 python library",
        subtype='DIR_PATH',
        default=""
        )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "python_path")

@orientation_helper(axis_forward='-Z', axis_up='Y')
class MitsubaFileExport(Operator, ExportHelper):
    """Export as a Mitsuba 2 scene"""
    bl_idname = "export_scene.mitsuba2"
    bl_label = "Mitsuba 2 Export"

    filename_ext = ".xml"

    use_selection: BoolProperty(
	        name="Selection Only",
	        description="Export selected objects only",
	        default=False,
	    )

    def __init__(self):
        self.reset()

    def reset(self):
        self.export_ctx = FileExportContext()
        self.geometry_exporter = GeometryExporter()

    def set_python_path(self, context):
        # set path to mitsuba
        prefs = bpy.context.preferences.addons[__package__].preferences
        if prefs.python_path != "":
            sys.path.append(bpy.path.abspath(prefs.python_path))
        elif getenv('PYTHONPATH'):
            tokens = getenv('PYTHONPATH').split(':')
            for token in tokens: #add the paths to python path
                sys.path.append(token)

    def execute(self, context):
        # Make sure we can load mitsuba from blender
        self.set_python_path(context)
        try:
            import mitsuba
            mitsuba.set_variant('scalar_rgb')
        except ModuleNotFoundError:
            self.report({'ERROR'}, "Importing Mitsuba failed. Please verify the path to the library.")
            return {'CANCELLED'}

        # Conversion matrix to shift the "Up" Vector. This can be useful when exporting single objects to an existing mitsuba scene.
        axis_mat = axis_conversion(
	            to_forward=self.axis_forward,
	            to_up=self.axis_up,
	        ).to_4x4()
        self.export_ctx.axis_mat = axis_mat

        self.export_ctx.set_filename(self.filepath)
        #TODO: move this
        self.export_ctx.add_comment("Integrator")
        integrator = {'plugin':'integrator', 'type':'path'}
        self.export_ctx.data_add(integrator)
        #even though cameras are not added here, we add the comment here because the rest will be moved when writing the XML file
        self.export_ctx.add_comment("Cameras")

        depsgraph = context.evaluated_depsgraph_get()#TODO: get RENDER evaluated depsgraph (not implemented)
        b_scene = context.scene #TODO: what if there are multiple scenes?
        export_world(self.export_ctx, b_scene.world)

        #main export loop
        for object_instance in depsgraph.object_instances:
            if self.use_selection:
                #skip if it's not selected or if it's an instance and the parent object is not selected
                if not object_instance.is_instance and not object_instance.object.original.select_get():
                    continue
                if object_instance.is_instance and not object_instance.object.parent.original.select_get():
                    continue

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
