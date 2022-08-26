import bpy

def mitsuba_menu_import(self, context):
    self.layout.operator('mitsuba.scene_import', text="Mitsuba (.xml)")

def register():
    bpy.types.TOPBAR_MT_file_import.append(mitsuba_menu_import)

def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(mitsuba_menu_import)
