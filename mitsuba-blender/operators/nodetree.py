import bpy
from bpy.props import IntProperty

from .utils import (
    init_mitsuba_material_node_tree, show_mitsuba_node_tree
)

class MITSUBA_OT_material_node_tree_show(bpy.types.Operator):
    '''
    Operator that displays a Mitsuba node tree inside of the shader editor
    '''
    bl_idname = 'mitsuba.material_node_tree_show'
    bl_label = 'Show Nodes'
    bl_description = 'Switch to the node tree of this material'

    @classmethod
    def poll(cls, context):
        obj = context.object
        if not obj:
            return False

        mat = obj.active_material
        if not mat:
            return False

        return mat.mitsuba.node_tree

    def execute(self, context):
        mat = context.active_object.active_material
        node_tree = mat.mitsuba.node_tree

        if show_mitsuba_node_tree(context, node_tree):
            return {'FINISHED'}

        self.report({'ERROR'}, 'Open the node editor first')
        return {'CANCELLED'}

class MITSUBA_OT_material_node_tree_new(bpy.types.Operator):
    '''
    Operator that creates a new Mitsuba node tree
    '''
    bl_idname = 'mitsuba.material_node_tree_new'
    bl_label = 'New'
    bl_description = 'Create a material node tree'
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.object

    def execute(self, context):
        mat = context.object.active_material
        if mat:
            name = f'Nodes_{mat.name}'
        else:
            name = 'Material Node Tree'

        node_tree = bpy.data.node_groups.new(name=name, type='mitsuba_material_nodes')
        init_mitsuba_material_node_tree(node_tree)

        if mat:
            mat.mitsuba.node_tree = node_tree

        show_mitsuba_node_tree(context, node_tree)
        return {'FINISHED'}

class MITSUBA_OT_material_node_tree_set(bpy.types.Operator):
    '''
    Operator that sets the node tree of a given material
    '''
    bl_idname = 'mitsuba.material_node_tree_set'
    bl_label = ''
    bl_description = 'Assign this node tree'
    bl_options = {'UNDO'}

    node_tree_index: IntProperty()

    @classmethod
    def poll(cls, context):
        if not hasattr(context, 'material'):
            return False
        return context.material and not context.material.library

    def execute(self, context):
        mat = context.material
        node_tree = bpy.data.node_groups[self.node_tree_index]
        mat.mitsuba.node_tree = node_tree
        return {"FINISHED"}
