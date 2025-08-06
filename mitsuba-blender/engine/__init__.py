import bpy
from .final import MitsubaRenderEngine

def get_panels():
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

def register():
    from . import properties
    from . import panels
    properties.register()
    panels.register()
    bpy.utils.register_class(MitsubaRenderEngine)
    for panel in get_panels():
        panel.COMPAT_ENGINES.add('MITSUBA')

def unregister():
    from . import properties
    from . import panels
    properties.unregister()
    panels.unregister()
    bpy.utils.unregister_class(MitsubaRenderEngine)
    for panel in get_panels():
        if 'MITSUBA' in panel.COMPAT_ENGINES:
            panel.COMPAT_ENGINES.remove('MITSUBA')
