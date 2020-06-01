import bpy
from .export import MitsubaFileExport

def menu_func(self, context):
    self.layout.operator(MitsubaFileExport.bl_idname, text="Mitsuba 2 (.xml)")

def register():
    bpy.utils.register_class(MitsubaFileExport)
    bpy.types.TOPBAR_MT_file_export.append(menu_func)

def unregister():
    bpy.utils.unregister_class(MitsubaFileExport)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func)