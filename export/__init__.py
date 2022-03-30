import bpy
import os
import sys
from .export import MitsubaFileExport
from .importer import MitsubaFileImport

def menu_export_func(self, context):
    self.layout.operator(MitsubaFileExport.bl_idname, text="Mitsuba 2 (.xml)")

def menu_import_func(self, context):
    self.layout.operator(MitsubaFileImport.bl_idname, text="Mitsuba 2 (.xml)")

def register():
    bpy.utils.register_class(MitsubaFileExport)
    bpy.utils.register_class(MitsubaFileImport)
    bpy.types.TOPBAR_MT_file_export.append(menu_export_func)
    bpy.types.TOPBAR_MT_file_import.append(menu_import_func)

def unregister():
    bpy.utils.unregister_class(MitsubaFileExport)
    bpy.utils.unregister_class(MitsubaFileImport)
    bpy.types.TOPBAR_MT_file_export.remove(menu_export_func)
    bpy.types.TOPBAR_MT_file_import.remove(menu_import_func)
