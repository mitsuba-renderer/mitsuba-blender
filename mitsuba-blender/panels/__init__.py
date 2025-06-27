'''
Inspired from blender/intern/cycles/blender/addon/ui.py
'''

import bpy

from .addon import *
from .materials import *
from .lights import *

def node_panel(cls):
    '''
    Adapt properties editor panel to display in node editor. We have to
    copy the class rather than inherit due to the way bpy registration works.
    '''
    node_cls = type('NODE_' + cls.__name__, cls.__bases__, dict(cls.__dict__))

    node_cls.bl_space_type = 'NODE_EDITOR'
    node_cls.bl_region_type = 'UI'
    node_cls.bl_category = "Options"
    if hasattr(node_cls, 'bl_parent_id'):
        node_cls.bl_parent_id = 'NODE_' + node_cls.bl_parent_id

    return node_cls

def get_mitsuba_compatible_panels():
    '''
    List all panels that are compatible with the Mitsuba engine
    '''
    exclude_panels = {
        'VIEWLAYER_PT_filter',
        'VIEWLAYER_PT_layer_passes',
        'RENDER_PT_simplify',
        'RENDER_PT_color_management',
        'RENDER_PT_freestyle',
        'RENDER_PT_gpencil'
    }

    panels = []
    for panel in bpy.types.Panel.__subclasses__():
        if hasattr(panel, 'COMPAT_ENGINES') and 'BLENDER_RENDER' in panel.COMPAT_ENGINES:
            if panel.__name__ not in exclude_panels:
                panels.append(panel)
    return panels

classes = (
    MITSUBA_PT_context_material,
    MITSUBA_MATERIAL_PT_surface,
    MITSUBA_LIGHT_PT_preview,
    MITSUBA_LIGHT_PT_light,
    MITSUBA_LIGHT_PT_nodes,
    MITSUBA_LIGHT_PT_beam_shape,
    node_panel(MITSUBA_LIGHT_PT_light),
    node_panel(MITSUBA_LIGHT_PT_beam_shape)
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    # Add Mitsuba to the compatible engines for the panels listed above
    for panel in get_mitsuba_compatible_panels():
        panel.COMPAT_ENGINES.add('Mitsuba')

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

    # Remove Mitsuba to the compatible engines for the panels listed above
    for panel in get_mitsuba_compatible_panels():
        if 'Mitsuba' in panel.COMPAT_ENGINES:
            panel.COMPAT_ENGINES.remove('Mitsuba')
