import bpy

from .camera import *
from .integrator import *

def draw_device(self, context):
    scene = context.scene
    layout = self.layout
    layout.use_property_split = True
    layout.use_property_decorate = False

    if context.engine == 'Mitsuba':
        mitsuba_settings = scene.mitsuba_engine

        col = layout.column()
        col.prop(mitsuba_settings, "variant")
        col.prop(mitsuba_settings, "render_progressive", text="Enable progressive rendering")
        col.prop(mitsuba_settings, "debug_mode", text="Debug mode")

        import mitsuba as mi
        if mitsuba_settings.debug_mode:
            mi.set_log_level(mi.LogLevel.Debug)
        else:
            mi.set_log_level(mi.LogLevel.Error)

def register():
    from .engine import MITSUBA_VIEWPORT_PT_engine, MitsubaRenderSettings

    bpy.types.RENDER_PT_context.append(draw_device)
    bpy.utils.register_class(MitsubaRenderSettings)
    bpy.utils.register_class(MitsubaCameraSettings)
    bpy.utils.register_class(MITSUBA_RENDER_PT_integrator)
    bpy.utils.register_class(MITSUBA_CAMERA_PT_sampler)
    bpy.utils.register_class(MITSUBA_CAMERA_PT_rfilter)
    bpy.utils.register_class(MITSUBA_VIEWPORT_PT_engine)

def unregister():
    from .engine import MITSUBA_VIEWPORT_PT_engine, MitsubaRenderSettings

    bpy.types.RENDER_PT_context.remove(draw_device)
    bpy.utils.unregister_class(MitsubaRenderSettings)
    bpy.utils.unregister_class(MitsubaCameraSettings)
    bpy.utils.unregister_class(MITSUBA_RENDER_PT_integrator)
    bpy.utils.unregister_class(MITSUBA_CAMERA_PT_sampler)
    bpy.utils.unregister_class(MITSUBA_CAMERA_PT_rfilter)
    bpy.utils.unregister_class(MITSUBA_VIEWPORT_PT_engine)