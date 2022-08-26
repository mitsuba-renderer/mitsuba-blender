from bpy.utils import register_class, unregister_class

from . import (
    material, nodetree, scene
)

classes = (
    material.MITSUBA_OT_material_new,
    material.MITSUBA_OT_material_unlink,
    material.MITSUBA_OT_material_copy,
    material.MITSUBA_OT_material_select,
    nodetree.MITSUBA_OT_material_node_tree_show,
    nodetree.MITSUBA_OT_material_node_tree_new,
    nodetree.MITSUBA_OT_material_node_tree_set,
    scene.MITSUBA_OT_scene_init_empty,
    scene.MITSUBA_OT_scene_import,
    scene.MITSUBA_OT_scene_export,
)

def register():
    for cls in classes:
        register_class(cls)

def unregister():
    for cls in classes:
        unregister_class(cls)
