from bpy.utils import register_class, unregister_class
from . import (
    material, node_editor, exporter, importer
)

classes = (
    material.MITSUBA_PT_context_material,
    node_editor.MITSUBA_MATERIAL_MT_node_tree,
)

def register():
    node_editor.register()
    exporter.register()
    importer.register()
    for cls in classes:
        register_class(cls)

def unregister():
    node_editor.unregister()
    exporter.unregister()
    importer.unregister()
    for cls in classes:
        unregister_class(cls)
