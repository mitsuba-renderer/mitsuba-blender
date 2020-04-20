bl_info = {
    "name": "Mitsuba2-Blender",
    "author": "Baptiste Nicolet",
    "version": (0, 1),
    "blender": (2, 80, 0),
    "category": "Exporter",
    "location": "File > Export > Mitsuba 2",
    "description": "Mitsuba2 export for Blender",
    "warning": "alpha0",
    "support": "TESTING"
}

import bpy
from .export import MitsubaFileExport, MitsubaPrefs

def menu_func(self, context):
    self.layout.operator(MitsubaFileExport.bl_idname, text="Mitsuba 2 (.xml)")

def register():
    bpy.utils.register_class(MitsubaFileExport)
    bpy.utils.register_class(MitsubaPrefs)
    bpy.types.TOPBAR_MT_file_export.append(menu_func)

def unregister():
    bpy.utils.unregister_class(MitsubaFileExport)
    bpy.utils.unregister_class(MitsubaPrefs)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func)

if __name__ == '__main__':
    register()