from bl_ui.properties_material import MaterialButtonsPanel
from bpy.types import Panel, Menu

def mi_mat_template_ID(layout, material):
    row = layout.row(align=True)
    row.operator('mitsuba.material_select', icon='MATERIAL', text='')

    if material:
        row.prop(material, 'name', text='')
        if material.users > 1:
            row.operator('mitsuba.material_copy', text=str(material.users))
        #row.prop(material, "use_fake_user", text="")
        row.operator('mitsuba.material_copy', text='', icon='DUPLICATE')
        row.operator('mitsuba.material_unlink', text='', icon='X')
    else:
        row.operator('mitsuba.material_new', text='New', icon='ADD')
    return row

class MITSUBA_PT_context_material(MaterialButtonsPanel, Panel):
    '''
    Custom UI panel that displays Mitsuba material options
    '''
    bl_label = ''
    bl_options = { 'HIDE_HEADER' }
    bl_order = 1
    COMPAT_ENGINES = { 'MITSUBA' }

    @classmethod
    def poll(cls, context):
        return (context.material or context.object) and context.scene.render.engine in cls.COMPAT_ENGINES

    def draw(self, context):
        layout = self.layout
        mat = context.material
        obj = context.object
        slot = context.material_slot
        space = context.space_data

        if obj:
            is_sortable = len(obj.material_slots) > 1
            rows = 1
            if (is_sortable):
                rows = 4

            row = layout.row()

            row.template_list('MATERIAL_UL_matslots', '', obj, 'material_slots', obj, 'active_material_index', rows=rows)

            col = row.column(align=True)
            col.operator('object.material_slot_add', icon='ADD', text='')
            col.operator('object.material_slot_remove', icon='REMOVE', text='')

            col.menu('MATERIAL_MT_context_menu', icon='DOWNARROW_HLT', text='')

            if is_sortable:
                col.separator()

                col.operator('object.material_slot_move', icon='TRIA_UP', text='').direction = 'UP'
                col.operator('object.material_slot_move', icon='TRIA_DOWN', text='').direction = 'DOWN'

            if obj.mode == 'EDIT':
                row = layout.row(align=True)
                row.operator('object.material_slot_assign', text='Assign')
                row.operator('object.material_slot_select', text='Select')
                row.operator('object.material_slot_deselect', text='Deselect')

            if obj:
                # Note that we don't use layout.template_ID() because we can't
                # control the copy operator in that template.
                # So we mimic our own template_ID.
                row = mi_mat_template_ID(layout, obj.active_material)
                if slot:
                    row = row.row()
                    row.prop(slot, 'link', text='')
                else:
                    row.label()
            elif mat:
                layout.template_ID(space, 'pin_id')
                layout.separator()

            if mat:
                if mat.mitsuba.node_tree:
                    layout.operator('mitsuba.material_node_tree_show', icon='NODETREE')
                else:
                    layout.operator("mitsuba.material_node_tree_new", icon='NODETREE', text="Use Mitsuba Material Nodes")
