import bpy

def mitsuba_menu_export(self, context):
    self.layout.operator('mitsuba.scene_export', text="Mitsuba (.xml)")

def register():
    bpy.types.TOPBAR_MT_file_export.append(mitsuba_menu_export)

def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(mitsuba_menu_export)
