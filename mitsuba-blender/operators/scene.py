import bpy
from bpy.props import StringProperty, BoolProperty
from bpy_extras.io_utils import ImportHelper, ExportHelper, orientation_helper, axis_conversion

from ..importer import load_mitsuba_scene
from ..exporter import SceneConverter

import traceback

class MITSUBA_OT_scene_init_empty(bpy.types.Operator):
    '''
    Operator that initializes a new empty scene
    '''
    bl_idname = 'mitsuba.scene_init_empty'
    bl_label = 'Init Empty Scene'
    bl_description = 'Initialize a new empty scene'
    bl_options = { 'UNDO' }

    name: StringProperty(
        name = 'New Scene Name',
        description = 'Name of the newly created scene. If a scene with the same name '
                      'already exists, it will be cleared.',
        default = 'Mitsuba',
    )

    def execute(self, context):
        # Create a temporary scene in order to guarantee that at least one scene
        # exists. This is required by Blender.
        tmp_scene = bpy.data.scenes.new('mi-tmp')

        # Check if the scene already exists
        bl_scene = bpy.data.scenes.get(self.name)
        if bl_scene is not None:
            # Delete the scene if it exists
            bpy.data.scenes.remove(bl_scene)
            # Clear all orphaned data
            bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)

        bpy.data.scenes.new(self.name)

        # Delete the temporary scene
        bpy.data.scenes.remove(tmp_scene)

        return { 'FINISHED' }

@orientation_helper(axis_forward='-Z', axis_up='Y')
class MITSUBA_OT_scene_import(bpy.types.Operator, ImportHelper):
    ''' Import a Mitsuba scene '''
    bl_idname = 'mitsuba.scene_import'
    bl_label = 'Import Mitsuba Scene'

    filename_ext = '.xml'
    filter_glob: StringProperty(default='*.xml', options={'HIDDEN'})

    override_scene: BoolProperty(
        name = 'Override Current Scene',
        description = 'Override the current scene with the imported Mitsuba scene. '
                      'Otherwise, creates a new scene for Mitsuba objects.',
        default = True,
    )

    create_cycles_node_tree: BoolProperty(
        name = 'Create Cycles Node Tree',
        description = 'Convert materials into Cycles node trees (experimental).',
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

        new_scene_name = bpy.context.scene.name if self.override_scene else 'Mitsuba'
        bpy.ops.mitsuba.scene_init_empty(name=new_scene_name)
        
        scene = bpy.data.scenes.get(new_scene_name)
        collection = scene.collection

        # Set the allocated scene as the currently active one
        # NOTE: This needs to be done before trying to load the scene as
        #       the other way around leads to a segmentation fault.
        bpy.context.window.scene = scene

        try:
            load_mitsuba_scene(context, scene, collection, self.filepath, axis_mat, self.create_cycles_node_tree)
        except RuntimeError:
            traceback.print_exc()
            self.report({'ERROR'}, "Failed to load Mitsuba scene. See error log.")
            return {'CANCELLED'}

        self.report({'INFO'}, "Scene imported successfully.")

        return {'FINISHED'}

@orientation_helper(axis_forward='-Z', axis_up='Y')
class MITSUBA_OT_scene_export(bpy.types.Operator, ExportHelper):
    """Export as a Mitsuba scene"""
    bl_idname = "mitsuba.scene_export"
    bl_label = "Export Mitsuba Scene"

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

    def __init__(self):
        self.reset()

    def reset(self):
        self.converter = SceneConverter()

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
        #write data to scene .xml file
        self.converter.dict_to_xml()

        window_manager.progress_end()

        self.report({'INFO'}, "Scene exported successfully!")

        #reset the exporter
        self.reset()

        return {'FINISHED'}
