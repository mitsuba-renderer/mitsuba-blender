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

def get_mitsuba_path():
    # Try to get the path to the Mitsuba 2 root folder
    tokens = os.getenv('MITSUBA_DIR')
    if tokens:
        for token in tokens.split(':'):
            path = os.path.join(token, 'build')
            if os.path.isdir(path):
                return path
    return ""

class MitsubaPrefs(AddonPreferences):

    bl_idname = __package__

    mitsuba_path: StringProperty(
        name="Build Path",
        description="Path to the Mitsuba 2 build directory",
        subtype='DIR_PATH',
        default=get_mitsuba_path()
        )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "mitsuba_path")

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

    def set_path(self, mts_build):
        '''
        Set the different variables necessary to run the addon properly.
        Add the path to mitsuba binaries to the PATH env var.
        Append the path to the python libs to sys.path

        Params
        ------

        mts_build: Path to mitsuba 2 build folder.
        '''
        os.environ['PATH'] += os.pathsep + os.path.join(mts_build, 'dist')
        sys.path.append(os.path.join(mts_build, 'dist', 'python'))

    def execute(self, context):
        # set path to mitsuba
        self.set_path(bpy.path.abspath(self.prefs.mitsuba_path))
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

        # Switch to object mode before exporting stuff, so everything is defined properly
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')

        integrator = {
            'type':'path',
            'max_depth': context.scene.cycles.max_bounces
            }
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
                self.export_ctx.log("Object: {} is hidden for render. Ignoring it.".format(evaluated_obj.name), 'INFO')
                continue#ignore it since we don't want it rendered (TODO: hide_viewport)

            if object_type in {'MESH', 'FONT', 'SURFACE', 'META'}:
                self.geometry_exporter.export_object(object_instance, self.export_ctx)
            elif object_type == 'CAMERA':
                export_camera(context, object_instance, b_scene, self.export_ctx)#TODO: investigate multiple scenes and multiple cameras at same time
            elif object_type == 'LIGHT':
                export_light(object_instance, self.export_ctx)
            else:
                self.export_ctx.log("Object: %s of type '%s' is not supported!" % (evaluated_obj.name_full, object_type), 'WARN')

        #write data to scene .xml file
        self.export_ctx.write()
        #reset the exporter
        self.reset()
        return {'FINISHED'}
