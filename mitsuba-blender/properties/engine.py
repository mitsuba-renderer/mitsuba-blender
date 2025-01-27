from __future__ import annotations # Delayed parsing of type annotations

import bpy
from bpy.props import *
from bpy.types import PropertyGroup

from .common import integrator_data, create_plugin_props

class MitsubaRenderSettings(PropertyGroup):
    '''
    Mitsuba main rendering properties
    It creates classes for each plugin described in the JSON files dynamically.
    '''
    import mitsuba as mi
    from mitsuba import config

    enum_variants = []
    for var in mi.variants():
        if not var.startswith('scalar'):
            enum_variants.append((var, var, ""))

    default_variant = mi.variant()

    variant : EnumProperty(
        name = "Variant",
        items = enum_variants,
        default = default_variant
    )
    # TODO: break variant into its subcomponents (backend/color/polarization/precision)
    enum_integrators = [(name, integrator['label'], integrator['description']) for name, integrator in integrator_data.items()]

    active_integrator : EnumProperty(
        name = "Integrator",
        items = enum_integrators,
        default = "path"
    )
    # Dynamic class for integrator parameters
    IntegratorProperties = type("IntegratorProperties",
        (PropertyGroup, ),
        {
            '__annotations__' : {
                # One entry per integrator plugin
                name : PointerProperty(type=create_plugin_props(name, integrator)) for name, integrator in integrator_data.items()
            }
        }
    )
    bpy.utils.register_class(IntegratorProperties)
    available_integrators : PointerProperty(type = IntegratorProperties)

    render_progressive: BoolProperty(
        name = 'render_progressive',
        description = 'Enable progressive rendering',
        default = True,
    )

    debug_mode: BoolProperty(
        name = 'debug_mode',
        description = 'Enable more verbose prints in the console',
        default = False,
    )

    viewport_res_scale: EnumProperty(
        name = 'viewport_res_scale',
        description = 'Scaling factor for the viewport rendering resolution',
        items=[
            ("0.125", "0.125", "0.125"),
            ("0.25", "0.25", "0.25"),
            ("0.5", "0.5", "0.5"),
            ("1", "1", "1"),
        ],
        default = "1",
    )

    viewport_progressive: BoolProperty(
        name = 'viewport_progressive',
        description = 'Enable progressive rendering',
        default = True,
    )

    viewport_max_spp: EnumProperty(
        name = 'viewport_max_spp',
        description = 'Maximum samples per pixel with progressive rendering',
        items=[tuple([str(v)] * 3) for v in [2, 4, 8, 16, 32, 64, 128, 256, 512]],
        default = "32",
    )

    viewport_enum_integrators = [
        (name, integrator['label'], integrator['description'])
        for name, integrator in integrator_data.items()
        if name in ['direct', 'path']
    ]

    def update_viewport_integrator(self, context):
        if hasattr(getattr(self.viewport_available_integrators, self.viewport_active_integrator), 'hide_emitters'):
            getattr(self.viewport_available_integrators, self.viewport_active_integrator).hide_emitters = False
        self.viewport_max_spp = '32'

    viewport_active_integrator : EnumProperty(
        name = "Integrator",
        items = viewport_enum_integrators,
        default = 'direct',
        update = update_viewport_integrator,
    )
    viewport_available_integrators : PointerProperty(type = IntegratorProperties)

    def update_viewport_max_depth(self, context):
        self.viewport_max_depth = max(self.viewport_max_depth, -1)

    viewport_disabled: BoolProperty(
        name = 'viewport_disabled',
        description = 'Disable viewport',
        default = False,
    )

    @classmethod
    def register(cls):
        bpy.types.Scene.mitsuba_engine = PointerProperty(
            name="Mitsuba Render Settings",
            description="Mitsuba render settings",
            type=cls,
        )

    @classmethod
    def unregister(cls):
        del bpy.types.Scene.mitsuba_engine

class MITSUBA_VIEWPORT_PT_engine(bpy.types.Panel):
    bl_idname = "MITSUBA_VIEWPORT_PT_engine"
    bl_label = "Viewport"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'render'
    COMPAT_ENGINES = { 'Mitsuba' }

    @classmethod
    def poll(cls, context):
        return context.engine in cls.COMPAT_ENGINES

    def draw(self, context):
        layout = self.layout
        mitsuba_settings = context.scene.mitsuba_engine
        layout.prop(mitsuba_settings, "viewport_progressive", text="Enable progressive rendering")
        layout.prop(mitsuba_settings, "viewport_max_spp", text="Maximum spp")
        layout.prop(mitsuba_settings, "viewport_res_scale", text="Resolution scale")
        layout.separator(type='LINE')
        layout.prop(mitsuba_settings, "viewport_active_integrator", text="Integrator")
        getattr(mitsuba_settings.viewport_available_integrators, mitsuba_settings.viewport_active_integrator).draw(layout)