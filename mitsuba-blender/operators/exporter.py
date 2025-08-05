
import bpy
from bpy.props import *
from bpy_extras.io_utils import ExportHelper, orientation_helper, axis_conversion

from .. import exporter
from .. import logging

@orientation_helper(axis_forward='-Z', axis_up='Y')
class ExportMitsubaBase(bpy.types.Operator, ExportHelper):
    '''
    Base class for Mitsuba exporter operator
    '''
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

    ignore_default_background: BoolProperty(
        name = "Ignore Default Background",
        description = "Ignore blender's default constant gray background when exporting to Mitsuba.",
        default = True
    )

    export_assets: BoolProperty(
        name = "Export assets",
        description = "If false, only write out the final Mitsuba xml scene file",
        default = True
    )

    def __init__(self):
        self.reset()

    def reset(self):
        self.converter = exporter.converter.SceneConverter()

    def export(self):
        raise Exception("Not implemented!")

    def execute(self, context):
        # Disable viewport while exporting
        context.scene.mitsuba_engine.viewport_disabled = True
        ctx = self.converter.ctx

        # Conversion matrix to shift the "Up" Vector. This can be useful when exporting single objects to an existing mitsuba scene.
        ctx.axis_mat = axis_conversion(
            to_forward=self.axis_forward,
            to_up=self.axis_up,
        ).to_4x4()

        # Add IDs to all base plugins (shape, emitter, sensor...)
        ctx.export_ids = self.export_ids
        ctx.use_selection = self.use_selection
        ctx.export_default_background = not self.ignore_default_background
        ctx.export_assets = self.export_assets

        self.converter.set_path(self.filepath)

        window_manager = context.window_manager

        depsgraph = context.evaluated_depsgraph_get()

        total_progress = len(depsgraph.object_instances)
        window_manager.progress_begin(0, total_progress)

        import mitsuba as mi

        b_scene = depsgraph.scene
        mi.set_variant(b_scene.mitsuba_engine.variant)

        self.thread_env = b_scene.thread_env
        with mi.ScopedSetThreadEnvironment(b_scene.thread_env):
            self.converter.scene_to_dict(depsgraph, window_manager)

        # Export the scene using child class export function
        self.export()

        window_manager.progress_end()

        logging.info("Scene exported successfully!")
        self.report({'INFO'}, "Scene exported successfully!")

        # Reset the exporter
        self.reset()

        # Re-enable viewport after exporting
        context.scene.mitsuba_engine.viewport_disabled = False

        return {'FINISHED'}

@orientation_helper(axis_forward='-Z', axis_up='Y')
class ExportMitsubaXML(ExportMitsubaBase):
    '''
    'Export as a Mitsuba scene to an XML file
    '''
    bl_idname = "export_scene.mitsuba_engine_xml"
    bl_label = "Mitsuba Export to XML"

    filename_ext = ".xml"
    filter_glob: StringProperty(default="*.xml", options={'HIDDEN'})

    def export(self):
        import mitsuba as mi
        with mi.ScopedSetThreadEnvironment(self.thread_env):
            xml_writer = mi.python.xml.WriteXML(
                self.converter.filename,
                exporter.converter.ExportContext.SUBFOLDERS,
                split_files=self.split_files
            )
            xml_writer.process(self.converter.ctx.scene_dict)
