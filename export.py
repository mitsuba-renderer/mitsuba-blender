import bpy
from bpy.types import Operator, AddonPreferences
from bpy.props import StringProperty, BoolProperty
import os
import sys

from .file_api import FileExportContext, Files
from .materials import export_world
from .geometry import GeometryExporter
from .lights import export_light
from .camera import export_camera

from bpy_extras.io_utils import ExportHelper, axis_conversion, orientation_helper

def get_python_path():
    #try to get the path to mitsuba python lib with the env var
    tokens = os.getenv('PYTHONPATH')
    if tokens:
        for token in tokens.split(':'):
            if os.path.isdir(token):
                return token
    return ""

class MitsubaPrefs(AddonPreferences):

    bl_idname = __package__

    python_path: StringProperty(
        name="Path to Mitsuba 2 python library",
        subtype='DIR_PATH',
        default=get_python_path()
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
	        name = "Selection Only",
	        description="Export selected objects only",
	        default = False,
	    )

    split_files: BoolProperty(
            name = "Split File",
            description = "Split scene XML file in smaller fragments",
            default = False
    )

    export_ids: BoolProperty(
            name = "Export IDs",
            description = "Add an 'id' field for each object (shape, emitter, camera...)",
            default = False
    )

    ignore_background: BoolProperty(
            name = "Ignore Default Background",
            description = "Ignore blender's default constant gray background when exporting to Mitsuba.",
            default = True
    )

    def __init__(self):
        self.reset()
        self.prefs = bpy.context.preferences.addons[__package__].preferences

    def reset(self):
        self.export_ctx = FileExportContext()
        self.geometry_exporter = GeometryExporter()

    def execute(self, context):
        # set path to mitsuba
        sys.path.append(bpy.path.abspath(self.prefs.python_path))
        # Make sure we can load mitsuba from blender
        try:
            import mitsuba
            mitsuba.set_variant('scalar_rgb')
        except ModuleNotFoundError:
            self.report({'ERROR'}, "Importing Mitsuba failed. Please verify the path to the library in the addon preferences.")
            return {'CANCELLED'}

        # Conversion matrix to shift the "Up" Vector. This can be useful when exporting single objects to an existing mitsuba scene.
        axis_mat = axis_conversion(
	            to_forward=self.axis_forward,
	            to_up=self.axis_up,
	        ).to_4x4()
        self.export_ctx.axis_mat = axis_mat
        self.export_ctx.export_ids = self.export_ids
        self.export_ctx.set_filename(self.filepath, split_files=self.split_files)

        integrator = {'type':'path'}
        self.export_ctx.data_add(integrator)

        depsgraph = context.evaluated_depsgraph_get()#TODO: get RENDER evaluated depsgraph (not implemented)
        b_scene = context.scene #TODO: what if there are multiple scenes?
        export_world(self.export_ctx, b_scene.world, self.ignore_background)

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
            if evaluated_obj.hide_render or object_instance.is_instance and evaluated_obj.parent.original.hide_render:
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
        self.export_ctx.write()
        #reset the exporter
        self.reset()
        return {'FINISHED'}
