from __future__ import annotations

# Inspired from blender\intern\cycles\blender\addon\ui.py

import bpy
from bpy_extras.node_utils import find_node_input
from bpy.types import Panel

class MitsubaButtonsPanel:
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "render"
    COMPAT_ENGINES = {'Mitsuba'}

    @classmethod
    def poll(cls, context):
        return context.engine in cls.COMPAT_ENGINES

#-------------------------------------------------------------------------------
# Materials
#-------------------------------------------------------------------------------

def panel_node_draw(layout, id_data, output_type, input_name):
    if not id_data.use_nodes:
        layout.operator("cycles.use_shading_nodes", icon='NODETREE')
        return False

    ntree = id_data.node_tree

    node = ntree.get_output_node('CYCLES')
    if node:
        input = find_node_input(node, input_name)
        if input:
            layout.template_node_view(ntree, node, input)
        else:
            layout.label(text="Incompatible output node")
    else:
        layout.label(text="No output node")

    return True

class Mitsuba_MATERIAL_PT_surface(MitsubaButtonsPanel, Panel):
    bl_label = "Surface"
    bl_context = "material"

    @classmethod
    def poll(cls, context):
        mat = context.material
        return mat and (not mat.grease_pencil) and MitsubaButtonsPanel.poll(context)

    def draw(self, context):
        layout = self.layout

        layout.use_property_split = True

        mat = context.material
        if not panel_node_draw(layout, mat, 'OUTPUT_MATERIAL', 'Surface'):
            layout.prop(mat, "diffuse_color")

class Mitsuba_PT_context_material(MitsubaButtonsPanel, Panel):
    bl_label = ""
    bl_context = "material"
    bl_options = {'HIDE_HEADER'}

    @classmethod
    def poll(cls, context):
        if context.active_object and context.active_object.type == 'GPENCIL':
            return False
        else:
            return (context.material or context.object) and MitsubaButtonsPanel.poll(context)

    def draw(self, context):
        layout = self.layout

        mat = context.material
        ob = context.object
        slot = context.material_slot
        space = context.space_data

        if ob:
            is_sortable = len(ob.material_slots) > 1
            rows = 3
            if (is_sortable):
                rows = 4

            row = layout.row()

            row.template_list("MATERIAL_UL_matslots", "", ob, "material_slots", ob, "active_material_index", rows=rows)

            col = row.column(align=True)
            col.operator("object.material_slot_add", icon='ADD', text="")
            col.operator("object.material_slot_remove", icon='REMOVE', text="")
            col.separator()
            col.menu("MATERIAL_MT_context_menu", icon='DOWNARROW_HLT', text="")

            if is_sortable:
                col.separator()

                col.operator("object.material_slot_move", icon='TRIA_UP', text="").direction = 'UP'
                col.operator("object.material_slot_move", icon='TRIA_DOWN', text="").direction = 'DOWN'

            if ob.mode == 'EDIT':
                row = layout.row(align=True)
                row.operator("object.material_slot_assign", text="Assign")
                row.operator("object.material_slot_select", text="Select")
                row.operator("object.material_slot_deselect", text="Deselect")

        row = layout.row()

        if ob:
            row.template_ID(ob, "active_material", new="material.new")

            if slot:
                icon_link = 'MESH_DATA' if slot.link == 'DATA' else 'OBJECT_DATA'
                row.prop(slot, "link", text="", icon=icon_link, icon_only=True)

        elif mat:
            layout.template_ID(space, "pin_id")
            layout.separator()


#-------------------------------------------------------------------------------
# Lights
#-------------------------------------------------------------------------------

class Mitsuba_LIGHT_PT_preview(MitsubaButtonsPanel, Panel):
    bl_label = "Preview"
    bl_context = "data"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return (
            context.light and
            not (
                context.light.type == 'AREA' and
                context.light.cycles.is_portal
            ) and
            MitsubaButtonsPanel.poll(context)
        )

    def draw(self, context):
        self.layout.template_preview(context.light)


class Mitsuba_LIGHT_PT_light(MitsubaButtonsPanel, Panel):
    bl_label = "Light"
    bl_context = "data"

    @classmethod
    def poll(cls, context):
        return context.light and MitsubaButtonsPanel.poll(context)

    def draw(self, context):
        layout = self.layout

        light = context.light
        clamp = light.cycles

        if self.bl_space_type == 'PROPERTIES':
            layout.row().prop(light, "type", expand=True)
            layout.use_property_split = True
        else:
            layout.use_property_split = True
            layout.row().prop(light, "type")

        col = layout.column()

        col.prop(light, "color")
        col.prop(light, "energy")
        col.separator()

        if light.type in {'POINT', 'SPOT'}:
            col.prop(light, "use_soft_falloff")
            col.prop(light, "shadow_soft_size", text="Radius")
        elif light.type == 'SUN':
            col.prop(light, "angle")
        elif light.type == 'AREA':
            col.prop(light, "shape", text="Shape")
            sub = col.column(align=True)

            if light.shape in {'SQUARE', 'DISK'}:
                sub.prop(light, "size")
            elif light.shape in {'RECTANGLE', 'ELLIPSE'}:
                sub.prop(light, "size", text="Size X")
                sub.prop(light, "size_y", text="Y")

        if not (light.type == 'AREA' and clamp.is_portal):
            col.separator()
            sub = col.column()
            sub.prop(clamp, "max_bounces")

        sub = col.column(align=True)
        sub.active = not (light.type == 'AREA' and clamp.is_portal)
        sub.prop(light, "use_shadow", text="Cast Shadow")
        sub.prop(clamp, "use_multiple_importance_sampling", text="Multiple Importance")

        if light.type == 'AREA':
            col.prop(clamp, "is_portal", text="Portal")


class Mitsuba_LIGHT_PT_nodes(MitsubaButtonsPanel, Panel):
    bl_label = "Nodes"
    bl_context = "data"

    @classmethod
    def poll(cls, context):
        return context.light and not (context.light.type == 'AREA' and
                                      context.light.cycles.is_portal) and \
            MitsubaButtonsPanel.poll(context)

    def draw(self, context):
        layout = self.layout

        layout.use_property_split = True

        light = context.light
        panel_node_draw(layout, light, 'OUTPUT_LIGHT', 'Surface')


class Mitsuba_LIGHT_PT_beam_shape(MitsubaButtonsPanel, Panel):
    bl_label = "Beam Shape"
    bl_parent_id = "Mitsuba_LIGHT_PT_light"
    bl_context = "data"

    @classmethod
    def poll(cls, context):
        if context.light.type in {'SPOT', 'AREA'}:
            return context.light and MitsubaButtonsPanel.poll(context)

    def draw(self, context):
        layout = self.layout
        light = context.light
        layout.use_property_split = True

        col = layout.column()
        if light.type == 'SPOT':
            col.prop(light, "spot_size", text="Spot Size")
            col.prop(light, "spot_blend", text="Blend", slider=True)
            col.prop(light, "show_cone")
        elif light.type == 'AREA':
            col.prop(light, "spread", text="Spread")

#-------------------------------------------------------------------------------
# Registration
#-------------------------------------------------------------------------------

# Adapt properties editor panel to display in node editor. We have to
# copy the class rather than inherit due to the way bpy registration works.
def node_panel(cls):
    node_cls = type('NODE_' + cls.__name__, cls.__bases__, dict(cls.__dict__))

    node_cls.bl_space_type = 'NODE_EDITOR'
    node_cls.bl_region_type = 'UI'
    node_cls.bl_category = "Options"
    if hasattr(node_cls, 'bl_parent_id'):
        node_cls.bl_parent_id = 'NODE_' + node_cls.bl_parent_id

    return node_cls

classes = (
    Mitsuba_PT_context_material,
    Mitsuba_MATERIAL_PT_surface,
    Mitsuba_LIGHT_PT_preview,
    Mitsuba_LIGHT_PT_light,
    Mitsuba_LIGHT_PT_nodes,
    Mitsuba_LIGHT_PT_beam_shape,
    node_panel(Mitsuba_LIGHT_PT_light),
    node_panel(Mitsuba_LIGHT_PT_beam_shape)
)

def register():
    from bpy.utils import register_class

    for cls in classes:
        register_class(cls)

def unregister():
    from bpy.utils import unregister_class

    for cls in classes:
        unregister_class(cls)
