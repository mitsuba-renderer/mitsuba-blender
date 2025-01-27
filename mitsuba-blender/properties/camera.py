import bpy
from bpy.props import *
from bpy.types import PropertyGroup

from .common import sampler_data, rfilter_data, create_plugin_props

class MITSUBA_CAMERA_PT_rfilter(bpy.types.Panel):
    bl_idname = "MITSUBA_CAMERA_PT_rfilter"
    bl_label = "Reconstruction Filter"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'render'
    def draw(self, context):
        layout = self.layout
        if hasattr(context.scene.camera, 'data'):
            cam_settings = context.scene.camera.data.mitsuba_engine
            layout.prop(cam_settings, "active_rfilter", text="Filter")
            getattr(cam_settings.rfilters, cam_settings.active_rfilter).draw(layout)

class MITSUBA_CAMERA_PT_sampler(bpy.types.Panel):
    bl_idname = "MITSUBA_CAMERA_PT_sampler"
    bl_label = "Sampler"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'render'
    def draw(self, context):
        layout = self.layout
        if hasattr(context.scene.camera, 'data'):
            cam_settings = context.scene.camera.data.mitsuba_engine
            layout.prop(cam_settings, "active_sampler", text="Sampler")
            getattr(cam_settings.samplers, cam_settings.active_sampler).draw(layout)

class MitsubaCameraSettings(PropertyGroup):
    '''
    Mitsuba main camera properties
    It creates classes for each plugin described in the JSON files for rfilters and samplers dynamically.
    '''
    enum_samplers = [(name, sampler['label'], sampler['description']) for name, sampler in sampler_data.items()]

    active_sampler : EnumProperty(
        name = "Sampler",
        items = enum_samplers,
        default = "independent"
    )

    # Dynamic class for sampler parameters
    SamplerProperties = type("SamplerProperties",
        (PropertyGroup, ),
        {
            '__annotations__' : {
                # One entry per sampler plugin
                name : PointerProperty(type=create_plugin_props(name, sampler)) for name, sampler in sampler_data.items()
            }
        }
    )
    bpy.utils.register_class(SamplerProperties)
    samplers : PointerProperty(type = SamplerProperties)

    enum_rfilters = [(name, rfilter['label'], rfilter['description']) for name, rfilter in rfilter_data.items()]

    active_rfilter : EnumProperty(
        name = "Reconstruction Filter",
        items = enum_rfilters,
        default = "box"
    )

    # Dynamic class for reconstruction filter parameters
    RfilterProperties = type("RfilterProperties",
        (PropertyGroup, ),
        {
            '__annotations__' : {
                # One entry per rfilter plugin
                name : PointerProperty(type=create_plugin_props(name, rfilter)) for name, rfilter in rfilter_data.items()
            }
        }
    )
    bpy.utils.register_class(RfilterProperties)
    rfilters : PointerProperty(type = RfilterProperties)

    @classmethod
    def register(cls):
        bpy.types.Camera.mitsuba_engine = PointerProperty(
            name="Mitsuba Camera Settings",
            description="Mitsuba camera settings",
            type=cls,
        )

    @classmethod
    def unregister(cls):
        del bpy.types.Camera.mitsuba_engine