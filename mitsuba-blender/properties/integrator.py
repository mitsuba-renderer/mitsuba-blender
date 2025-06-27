
import bpy
import os, json

class MITSUBA_RENDER_PT_integrator(bpy.types.Panel):
    bl_idname = "MITSUBA_RENDER_PT_integrator"
    bl_label = "Integrator"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'render'
    COMPAT_ENGINES = {'Mitsuba'}

    @classmethod
    def poll(cls, context):
        return context.engine in cls.COMPAT_ENGINES

    def draw(self, context):
        layout = self.layout
        mitsuba_settings = context.scene.mitsuba_engine
        layout.prop(mitsuba_settings, "active_integrator", text="Integrator")
        getattr(mitsuba_settings.available_integrators, mitsuba_settings.active_integrator).draw(layout)