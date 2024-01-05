if "bpy" in locals():
    import importlib
    if "bl_utils" in locals():
        importlib.reload(bl_utils)
    if "importer" in locals():
        importlib.reload(importer)
    if "exporter" in locals():
        importlib.reload(exporter)

import bpy
import time
from bpy.props import (
        StringProperty,
        BoolProperty,
        IntProperty,
    )
from bpy_extras.io_utils import (
        ImportHelper,
        ExportHelper,
        orientation_helper,
        axis_conversion
    )

from . import bl_utils
from . import importer
from . import exporter

@orientation_helper(axis_forward='-Z', axis_up='Y')
class ImportMistuba(bpy.types.Operator, ImportHelper):
    """Import a Mitsuba scene"""
    bl_idname = "import_scene.mitsuba"
    bl_label = "Mitsuba Import"

    filename_ext = ".xml"
    filter_glob: StringProperty(default="*.xml", options={'HIDDEN'})

    override_scene: BoolProperty(
        name = 'Override Current Scene',
        description = 'Override the current scene with the imported Mitsuba scene. '
                      'Otherwise, creates a new scene for Mitsuba objects.',
        default = True,
    )

    def execute(self, context):
        # Set blender to object mode
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')

        axis_mat = axis_conversion(
            to_forward=self.axis_forward,
            to_up=self.axis_up,
        ).to_4x4()

        if self.override_scene:
            # Clear the current scene
            scene = bl_utils.init_empty_scene(context, name=bpy.context.scene.name)
        else:
            # Create a new scene for Mitsuba objects
            scene = bl_utils.init_empty_scene(context, name='Mitsuba')
        collection = scene.collection

        try:
            importer.load_mitsuba_scene(context, scene, collection, self.filepath, axis_mat)
        except (RuntimeError, NotImplementedError) as e:
            print(e)
            self.report({'ERROR'}, "Failed to load Mitsuba scene. See error log.")
            return {'CANCELLED'}

        bpy.context.window.scene = scene

        self.report({'INFO'}, "Scene imported successfully.")

        return {'FINISHED'}


@orientation_helper(axis_forward='-Z', axis_up='Y')
class ExportMitsuba(bpy.types.Operator, ExportHelper):
    """Export as a Mitsuba scene"""
    bl_idname = "export_scene.mitsuba"
    bl_label = "Mitsuba Export"

    filename_ext = ".xml"
    filter_glob: StringProperty(default="*.xml", options={'HIDDEN'})

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

    bake_materials: BoolProperty(
        name = "Bake Materials",
        description = "Bakes Materials into textures. Takes longer to export scenes. Make sure GPU is enabled in settings",
        default = False
    )
    bake_mat_ids: BoolProperty(
        name = "Unique Material IDs",
        description = """If 'Bake Materials' is active bakes Materials with unique IDs. 
            Each object will have a unique material in final XML and will have correct blender representation.
            Otherwise some materials are reused and textures may be inaccurate""",
        default = False
    )

    bake_again: BoolProperty(
            name = "Bake textures again",
            description = """If 'Bake Materials' is active, this will bake the already existing textures if enabled. 
            This option allows to incrementally bake scene materials.""",
            default = True
    )

    bake_res_x: IntProperty(
        name = "Bake Resolution X",
        description = "Resultion size of X coordinate in pixels. If \"Bake Materials\" is enabled will bake with this resolution",
        default = 1024
    )

    bake_res_y: IntProperty(
        name = "Bake Resolution Y",
        description = "Resultion size of Y coordinate in pixels. If \"Bake Materials\" is enabled will bake with this resolution",
        default = 1024
    )

    def __init__(self):
        self.reset()

    def reset(self):
        self.converter = exporter.SceneConverter()

    def execute(self, context):
        start = time.time()
        # Conversion matrix to shift the "Up" Vector. This can be useful when exporting single objects to an existing mitsuba scene.
        axis_mat = axis_conversion(
	            to_forward=self.axis_forward,
	            to_up=self.axis_up,
	        ).to_4x4()

        self.converter.export_ctx.axis_mat = axis_mat
        # Add IDs to all base plugins (shape, emitter, sensor...)
        self.converter.export_ctx.export_ids = self.export_ids

        self.converter.use_selection = self.use_selection
        # Bake material feature options
        self.converter.export_ctx.bake_materials = self.bake_materials
        self.converter.export_ctx.bake_res_x = self.bake_res_x
        self.converter.export_ctx.bake_res_y = self.bake_res_y
        self.converter.export_ctx.bake_mat_ids = self.bake_mat_ids
        self.converter.export_ctx.bake_again = self.bake_again

        # Set path to scene .xml file
        self.converter.set_path(self.filepath, split_files=self.split_files)

        window_manager = context.window_manager

        deps_graph = context.evaluated_depsgraph_get()

        total_progress = len(deps_graph.object_instances)
        window_manager.progress_begin(0, total_progress)

        self.converter.scene_to_dict(deps_graph, window_manager)
        #write data to scene .xml file
        self.converter.dict_to_xml()

        window_manager.progress_end()

        self.report({'INFO'}, "Scene exported successfully!")

        #reset the exporter
        self.reset()
        end = time.time()
        self.converter.export_ctx.log(f"Export took {end-start}")
        return {'FINISHED'}


def menu_export_func(self, context):
    self.layout.operator(ExportMitsuba.bl_idname, text="Mitsuba (.xml)")

def menu_import_func(self, context):
    self.layout.operator(ImportMistuba.bl_idname, text="Mitsuba (.xml)")


classes = (
    ImportMistuba,
    ExportMitsuba
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.TOPBAR_MT_file_export.append(menu_export_func)
    bpy.types.TOPBAR_MT_file_import.append(menu_import_func)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

    bpy.types.TOPBAR_MT_file_export.remove(menu_export_func)
    bpy.types.TOPBAR_MT_file_import.remove(menu_import_func)
