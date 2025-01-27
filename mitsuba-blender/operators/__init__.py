import bpy

from .importer import ImportMitsubaXML
from .exporter import ExportMitsubaXML

def menu_import_xml_func(self, context):
    self.layout.operator(ImportMitsubaXML.bl_idname, text="Mitsuba (.xml)")

def menu_export_xml_func(self, context):
    self.layout.operator(ExportMitsubaXML.bl_idname, text="Mitsuba (.xml)")

classes = (
    ImportMitsubaXML,
    ExportMitsubaXML,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.TOPBAR_MT_file_import.append(menu_import_xml_func)
    bpy.types.TOPBAR_MT_file_export.append(menu_export_xml_func)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

    bpy.types.TOPBAR_MT_file_import.remove(menu_import_xml_func)
    bpy.types.TOPBAR_MT_file_export.remove(menu_export_xml_func)
