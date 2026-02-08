if "bpy" in locals():
    import importlib
    if "bl_utils" in locals():
        importlib.reload(bl_utils)
    if "importer" in locals():
        importlib.reload(importer)
    if "importer_yml" in locals():
        importlib.reload(importer_yml)
    if "exporter" in locals():
        importlib.reload(exporter)
    if "hdri_converter" in locals():
        importlib.reload(hdri_converter)

import bpy
from bpy.props import (
        StringProperty,
        BoolProperty,
    )
from bpy_extras.io_utils import (
        ImportHelper,
        ExportHelper,
        orientation_helper,
        axis_conversion
    )

from . import bl_utils
from . import importer
from . import importer_yml
from . import exporter
from . import hdri_converter


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
class ImportYMLConfig(bpy.types.Operator, ImportHelper):
    """Import a custom yml-description scene"""
    bl_idname = "import_scene.custom_yml"
    bl_label = "Custom YML Config Import"

    filename_ext = ".yml"
    filter_glob: StringProperty(default="*.yml", options={'HIDDEN'})

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

        if self.override_scene:
            # Clear the current scene
            scene = bl_utils.init_empty_scene(context, name=bpy.context.scene.name)
        else:
            # Create a new scene for Mitsuba objects
            scene = bl_utils.init_empty_scene(context, name='Mitsuba')

        try:
            importer_yml.build_new_scene(scene, self.filepath)
        except (RuntimeError, NotImplementedError) as e:
            print(e)
            self.report({'ERROR'}, "Failed to load scene from config. See error log.")
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reset()

    def reset(self):
        self.converter = exporter.SceneConverter()

    def execute(self, context):
        # Conversion matrix to shift the "Up" Vector. This can be useful when exporting single objects to an existing mitsuba scene.
        axis_mat = axis_conversion(
	            to_forward=self.axis_forward,
	            to_up=self.axis_up,
	        ).to_4x4()

        self.converter.export_ctx.axis_mat = axis_mat
        # Add IDs to all base plugins (shape, emitter, sensor...)
        self.converter.export_ctx.export_ids = self.export_ids

        self.converter.use_selection = self.use_selection

        # Set path to scene .xml file
        self.converter.set_path(self.filepath, split_files=self.split_files)

        window_manager = context.window_manager

        deps_graph = context.evaluated_depsgraph_get()

        total_progress = len(deps_graph.object_instances)
        window_manager.progress_begin(0, total_progress)

        self.converter.scene_to_dict(deps_graph, window_manager)
        # Write data to scene .xml file
        self.converter.dict_to_xml()

        window_manager.progress_end()

        self.report({'INFO'}, "Scene exported successfully!")

        # Reset the exporter
        self.reset()

        return {'FINISHED'}


@orientation_helper(axis_forward='-Z', axis_up='Y')
class ExportMitsubaExtended(bpy.types.Operator, ExportHelper):
    """Export the Mitsuba scene with auxiliary data"""
    bl_idname = "export_scene.mitsuba_optimization"
    bl_label = "Mitsuba Export For Optimization"

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
            default = True
    )

    ignore_background: BoolProperty(
            name = "Ignore Default Background",
            description = "Ignore blender's default constant gray background when exporting to Mitsuba.",
            default = True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reset()

    def reset(self):
        self.converter = exporter.SceneConverter(include_auxiliary_output=True)

    def execute(self, context):
        # Conversion matrix to shift the "Up" Vector. This can be useful when exporting single objects to an existing mitsuba scene.
        axis_mat = axis_conversion(
	            to_forward=self.axis_forward,
	            to_up=self.axis_up,
	        ).to_4x4()

        self.converter.export_ctx.axis_mat = axis_mat
        # Add IDs to all base plugins (shape, emitter, sensor...)
        self.converter.export_ctx.export_ids = self.export_ids

        self.converter.use_selection = self.use_selection

        # Set path to scene .xml file
        self.converter.set_path(self.filepath, split_files=self.split_files)

        window_manager = context.window_manager

        deps_graph = context.evaluated_depsgraph_get()

        total_progress = len(deps_graph.object_instances)
        window_manager.progress_begin(0, total_progress)

        self.converter.scene_to_dict(deps_graph, window_manager)
        # Write data to scene .xml file
        self.converter.dict_to_xml()
        # Write auxiliary output data to .yml file
        self.converter.aux_dict_to_yml()

        window_manager.progress_end()

        self.report({'INFO'}, "Scene exported successfully!")

        # Reset the exporter
        self.reset()

        return {'FINISHED'}



def menu_export_func(self, context):
    self.layout.operator(ExportMitsuba.bl_idname, text="Mitsuba (.xml)")

def menu_custom_export_func(self, context):
    self.layout.operator(ExportMitsubaExtended.bl_idname, text="Mitsuba (.xml) with Aux Data (.yml)")

def menu_import_func(self, context):
    self.layout.operator(ImportMistuba.bl_idname, text="Mitsuba (.xml)")

def menu_yml_import_func(self, context):
    self.layout.operator(ImportYMLConfig.bl_idname, text="Custom Config (.yml)")


classes = (
    ImportMistuba,
    ImportYMLConfig,
    ExportMitsuba,
    ExportMitsubaExtended
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.TOPBAR_MT_file_export.append(menu_export_func)
    bpy.types.TOPBAR_MT_file_export.append(menu_custom_export_func)
    bpy.types.TOPBAR_MT_file_import.append(menu_import_func)
    bpy.types.TOPBAR_MT_file_import.append(menu_yml_import_func)

    # Register HDRI converter
    hdri_converter.register()

def unregister():
    # Unregister HDRI converter
    hdri_converter.unregister()

    for cls in classes:
        bpy.utils.unregister_class(cls)

    bpy.types.TOPBAR_MT_file_export.remove(menu_export_func)
    bpy.types.TOPBAR_MT_file_export.append(menu_custom_export_func)
    bpy.types.TOPBAR_MT_file_import.remove(menu_import_func)
    bpy.types.TOPBAR_MT_file_import.append(menu_yml_import_func)
