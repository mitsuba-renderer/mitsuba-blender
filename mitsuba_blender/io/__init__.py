import os

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

    merge_shapes: BoolProperty(
        name = 'Merge Shapes',
        description = 'Merge all meshes with the same material into a single mesh.',
        default = False,
    )

    merge_plugins: BoolProperty(
        name = 'Merge Plugins',
        description = 'Merge equivalent plugins (e.g. materials). This does not apply to shapes.',
        default = True,
    )

    import_render_settings: BoolProperty(
        name = 'Import Render Settings',
        description = 'Apply the integrator, sampler, reconstruction filter and film '
                      'settings of the imported scene to the Mitsuba render properties.',
        default = False,
    )

    def execute(self, context):
        # Set blender to object mode
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')

        axis_mat = axis_conversion(
            to_forward=self.axis_forward,
            to_up=self.axis_up,
        ).to_4x4()

        # Parse the XML before any destructive scene change so a malformed
        # file cannot destroy the user's scene
        try:
            mi_state = importer.parse_mitsuba_scene(self.filepath, self.merge_shapes, self.merge_plugins)
        except Exception as e:
            print(e)
            self.report({'ERROR'}, "Failed to load Mitsuba scene. See error log.")
            return {'CANCELLED'}

        if self.override_scene:
            # Clear the current scene
            scene = bl_utils.init_empty_scene(name=bpy.context.scene.name)
        else:
            # Create a new scene for Mitsuba objects; Blender uniquifies
            # the name, keeping earlier imports intact
            scene = bpy.data.scenes.new('Mitsuba')
        collection = scene.collection

        try:
            warnings = importer.load_mitsuba_scene(scene, collection, self.filepath, axis_mat, self.merge_shapes, self.merge_plugins, self.import_render_settings, mi_state=mi_state)
        except Exception as e:
            print(e)
            self.report({'ERROR'}, "Failed to load Mitsuba scene. See error log.")
            return {'CANCELLED'}

        bpy.context.window.scene = scene

        if warnings:
            self.report({'WARNING'}, f"Scene imported with {len(warnings)} warnings (see console).")
        else:
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
        # Meshes and textures are written to subfolders of the target directory
        self.converter.export_ctx.directory = os.path.dirname(self.filepath)

        window_manager = context.window_manager

        deps_graph = context.evaluated_depsgraph_get()

        total_progress = len(deps_graph.object_instances)
        window_manager.progress_begin(0, total_progress)

        self.converter.scene_to_dict(deps_graph, window_manager, use_selection=self.use_selection, ignore_background=self.ignore_background)
        self.converter.dict_to_xml(self.filepath)

        window_manager.progress_end()

        warnings = self.converter.export_ctx.warnings
        if warnings:
            self.report({'WARNING'}, f"Scene exported with {len(warnings)} warnings (see console).")
        else:
            self.report({'INFO'}, "Scene exported successfully!")

        # Reset the exporter
        self.reset()

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
