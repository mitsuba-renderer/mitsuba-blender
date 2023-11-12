'''
Collection of operators available in Blender's material side panel
'''
import bpy
from bpy.props import EnumProperty

from .utils import (
    init_mitsuba_material_node_tree, show_mitsuba_node_tree
)

class MITSUBA_OT_material_new(bpy.types.Operator):
    '''
    Operator that creates a new Mitsuba material
    '''
    bl_idname = 'mitsuba.material_new'
    bl_label = 'New'
    bl_description = 'Create a new material and node tree'
    bl_options = { 'UNDO' }

    @classmethod
    def poll(cls, context):
        return context.object

    def execute(self, context):
        mat = bpy.data.materials.new(name='Material')
        node_tree = bpy.data.node_groups.new(name=f'Nodes_{mat.name}', type='mitsuba_material_nodes')
        init_mitsuba_material_node_tree(node_tree)
        mat.mitsuba.node_tree = node_tree

        obj = context.active_object
        if obj.material_slots:
            obj.material_slots[obj.active_material_index].material = mat
        else:
            obj.data.materials.append(mat)

        show_mitsuba_node_tree(context, node_tree)
        return {'FINISHED'}

class MITSUBA_OT_material_unlink(bpy.types.Operator):
    '''
    Operator that unlinks a Mitsuba material from the current object
    '''
    bl_idname = 'mitsuba.material_unlink'
    bl_label = ''
    bl_description = 'Unlink data-block'
    bl_options = { 'UNDO' }

    @classmethod
    def poll(cls, context):
        return context.object

    def execute(self, context):
        obj = context.active_object
        if obj.material_slots:
            obj.material_slots[obj.active_material_index].material = None
        return {'FINISHED'}

class MITSUBA_OT_material_copy(bpy.types.Operator):
    '''
    Operator that copies an existing Mitsuba material
    '''
    bl_idname = 'mitsuba.material_copy'
    bl_label = 'Copy'
    bl_description = 'Create a copy of the material (also copying the nodetree)'
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.object

    def execute(self, context):
        current_mat = context.active_object.active_material

        # Create a copy of the material
        new_mat = current_mat.copy()

        current_node_tree = current_mat.mitsuba.node_tree

        if current_node_tree:
            # Create a copy of the node_tree as well
            new_node_tree = current_node_tree.copy()
            new_node_tree.name = f'Nodes_{new_mat.name}'
            # Assign new node_tree to the new material
            new_mat.mitsuba.node_tree = new_node_tree

        context.active_object.active_material = new_mat

        return {'FINISHED'}


class MITSUBA_OT_material_select(bpy.types.Operator):
    '''
    Operator that selects a material from a drop-down menu
    '''
    bl_idname = 'mitsuba.material_select'
    bl_label = ''
    bl_property = 'material'

    callback_strings = []

    def callback(self, context):
        items = []

        for index, mat in enumerate(bpy.data.materials):
            #name = utils.get_name_with_lib(mat)
            name = mat.name
            # We can not show descriptions or icons here unfortunately
            items.append((str(index), name, ''))

        # There is a known bug with using a callback,
        # Python must keep a reference to the strings
        # returned or Blender will misbehave or even crash.
        MITSUBA_OT_material_select.callback_strings = items
        return items

    material: EnumProperty(name='Materials', items=callback)

    @classmethod
    def poll(cls, context):
        return context.object

    def execute(self, context):
        # Get the index of the selected material
        mat_index = int(self.material)
        mat = bpy.data.materials[mat_index]
        context.object.active_material = mat
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {'FINISHED'}
