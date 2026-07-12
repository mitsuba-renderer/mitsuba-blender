import bpy


class MitsubaPanel:
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    COMPAT_ENGINES = {'MITSUBA'}

    @classmethod
    def poll(cls, context):
        return context.engine in cls.COMPAT_ENGINES


class MITSUBA_RENDER_PT_integrator(MitsubaPanel, bpy.types.Panel):
    bl_idname = 'MITSUBA_RENDER_PT_integrator'
    bl_label = 'Integrator'
    bl_context = 'render'

    def draw(self, context):
        layout = self.layout
        settings = context.scene.mitsuba
        layout.prop(settings, 'active_integrator', text='Integrator')
        getattr(settings.available_integrators, settings.active_integrator).draw(layout)
        layout.prop(settings, 'custom_integrator')


class MITSUBA_CAMERA_PT_sampler(MitsubaPanel, bpy.types.Panel):
    bl_idname = 'MITSUBA_CAMERA_PT_sampler'
    bl_label = 'Sampler'
    bl_context = 'render'

    def draw(self, context):
        layout = self.layout
        camera = context.scene.camera
        if camera is None:
            layout.label(text='No active camera')
            return
        settings = camera.data.mitsuba
        layout.prop(settings, 'active_sampler', text='Sampler')
        getattr(settings.samplers, settings.active_sampler).draw(layout)


class MITSUBA_CAMERA_PT_rfilter(MitsubaPanel, bpy.types.Panel):
    bl_idname = 'MITSUBA_CAMERA_PT_rfilter'
    bl_label = 'Reconstruction Filter'
    bl_context = 'render'

    def draw(self, context):
        layout = self.layout
        camera = context.scene.camera
        if camera is None:
            layout.label(text='No active camera')
            return
        settings = camera.data.mitsuba
        layout.prop(settings, 'active_rfilter', text='Filter')
        getattr(settings.rfilters, settings.active_rfilter).draw(layout)


def draw_device(self, context):
    if context.engine != 'MITSUBA':
        return
    layout = self.layout
    layout.use_property_split = True
    layout.use_property_decorate = False
    layout.column().prop(context.scene.mitsuba, 'variant')


def get_compatible_panels():
    '''Built-in panels that should also show up for the Mitsuba engine.'''
    exclude_panels = {
        'VIEWLAYER_PT_filter',
        'VIEWLAYER_PT_layer_passes',
        'RENDER_PT_simplify',
        'RENDER_PT_color_management',
        'RENDER_PT_freestyle',
    }
    return [panel for panel in bpy.types.Panel.__subclasses__()
            if 'BLENDER_RENDER' in getattr(panel, 'COMPAT_ENGINES', ())
            and panel.__name__ not in exclude_panels]


classes = (
    MITSUBA_RENDER_PT_integrator,
    MITSUBA_CAMERA_PT_sampler,
    MITSUBA_CAMERA_PT_rfilter,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.RENDER_PT_context.append(draw_device)
    for panel in get_compatible_panels():
        panel.COMPAT_ENGINES.add('MITSUBA')


def unregister():
    for panel in get_compatible_panels():
        panel.COMPAT_ENGINES.discard('MITSUBA')
    bpy.types.RENDER_PT_context.remove(draw_device)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
