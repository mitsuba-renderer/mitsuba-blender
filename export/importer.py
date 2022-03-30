import bpy
from bpy.types import Operator, AddonPreferences
from bpy.props import StringProperty, BoolProperty
import os
from os.path import basename, dirname

from .convert import SceneConverter
from bpy_extras.io_utils import ImportHelper, axis_conversion, orientation_helper

@orientation_helper(axis_forward='-Z', axis_up='Y')
class MitsubaFileImport(Operator, ImportHelper):
    """Import a Mitsuba 2 scene"""
    bl_idname = "import_scene.mitsuba2"
    bl_label = "Mitsuba 2 Import"

    filename_ext = ".xml"
    filter_glob: StringProperty(default="*.xml", options={'HIDDEN'})

    def __init__(self):
        # addon_name must match the addon main folder name
        # Use dirname() to go up the necessary amount of folders
        addon_name = basename(dirname(dirname(__file__)))
        self.prefs = bpy.context.preferences.addons[addon_name].preferences
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
        
        # Set path to scene .xml file
        #self.converter.set_path(self.filepath, split_files=self.split_files)

        #window_manager = context.window_manager

        #deps_graph = context.evaluated_depsgraph_get()

        #total_progress = len(deps_graph.object_instances)
        #window_manager.progress_begin(0, total_progress)

        #self.converter.scene_to_dict(deps_graph, window_manager)
        #write data to scene .xml file
        #self.converter.dict_to_xml()

        #window_manager.progress_end()

        from mitsuba import xml_to_props

        raw_props = xml_to_props(self.filepath)
        props = {}
        for (class_, prop) in raw_props:
            props[prop.id()] = (class_, prop)

        from .camera import import_camera

        for (_, (class_, prop)) in props.items():
            if class_ == 'Sensor':
                import_camera(axis_mat, bpy.context.scene.collection, prop, props)
            else:
                raise NotImplementedError(f'Object class "{class_}" is not implemented.')

        self.report({'INFO'}, "Scene imported successfully!")

        #reset the exporter
        self.reset()
        return {'FINISHED'}
