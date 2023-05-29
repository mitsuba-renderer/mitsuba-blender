if "bpy" in locals():
    import importlib
    if "bl_utils" in locals():
        importlib.reload(bl_utils)
    if "importer" in locals():
        importlib.reload(importer)
    if "exporter" in locals():
        importlib.reload(exporter)

import bpy
import os, sys
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

sys.path.insert(1, '/home/youming/Desktop/mitsuba-blender/mitsuba-blender/io/')
import bl_utils
import importer
import exporter


"""Export as a Mitsuba scene"""
bl_idname = "export_scene.mitsuba"
bl_label = "Mitsuba Export"

filename_ext = ".xml"
filter_glob = StringProperty(default="*.xml", options={'HIDDEN'})

use_selection = False
split_files = False
export_ids = False
ignore_background = True

converter = exporter.SceneConverter()
context = bpy.context

axis_forward='-Z'
axis_up='Y'

# Conversion matrix to shift the "Up" Vector. This can be useful when exporting single objects to an existing mitsuba scene.
axis_mat = axis_conversion(
        to_forward=axis_forward,
        to_up=axis_up,
    ).to_4x4()

converter.export_ctx.axis_mat = axis_mat
# Add IDs to all base plugins (shape, emitter, sensor...)
converter.export_ctx.export_ids = export_ids

converter.use_selection = use_selection

filepath = '/home/youming/Desktop/test/test.xml'
# Set path to scene .xml file
converter.set_path(filepath, split_files=split_files)
# avoid rewrite interpolated texture over original ones

if 'textures' in os.listdir(os.path.split(filepath)[0]):
    converter.export_ctx.log('Change the output dir, texture and mesh are aleady in current path!', 'WARN')
    report({'INFO'}, "Scene export fail, please change the output dir!")
    sys.exit()
window_manager = context.window_manager

deps_graph = context.evaluated_depsgraph_get()

total_progress = len(deps_graph.object_instances)
window_manager.progress_begin(0, total_progress)

converter.scene_to_dict(deps_graph, window_manager)
#write data to scene .xml file
converter.dict_to_xml()

window_manager.progress_end()

print("Scene exported successfully!")
# sys.exit()