from . import mi_props_utils

def apply_mi_path_properties(mi_context, mi_props, bl_props=None):
    bl_integrator = mi_context.bl_scene.mitsuba if bl_props is None else bl_props
    bl_path_props = getattr(bl_integrator.available_integrators, 'path', None)
    if bl_path_props is None:
        mi_context.log(f'Mitsuba Integrator "path" is not supported.', 'ERROR')
        return False
    bl_integrator.active_integrator = 'path'
    bl_path_props.max_depth = mi_props.get('max_depth', -1)
    bl_path_props.rr_depth = mi_props.get('rr_depth', 5)
    bl_path_props.hide_emitters = mi_props.get('hide_emitters', False)

    # Cycles properties
    if bl_props is None:
        bl_renderer = mi_context.bl_scene.cycles
        bl_renderer.progressive = 'PATH'
        bl_max_bounces = mi_props.get('max_depth', 1024)
        bl_renderer.max_bounces = bl_max_bounces
        bl_renderer.diffuse_bounces = bl_max_bounces
        bl_renderer.glossy_bounces = bl_max_bounces
        bl_renderer.transparent_max_bounces = bl_max_bounces
        bl_renderer.transmission_bounces = bl_max_bounces
        bl_renderer.volume_bounces = bl_max_bounces
        bl_renderer.min_light_bounces = mi_props.get('rr_depth', 5)

    return True

def apply_mi_moment_properties(mi_context, mi_props, bl_props=None):
    if bl_props is not None:
        # FIXME: support moment integrator nesting
        mi_context.log('Mitsuba Integrator "moment" does not support being nested yet.', 'ERROR')
        return False

    mi_renderer = mi_context.bl_scene.mitsuba
    bl_moment_props = getattr(mi_renderer.available_integrators, 'moment', None)
    if bl_moment_props is None:
        mi_context.log(f'Mitsuba Integrator "moment" is not supported.', 'ERROR')
        return False
    # Mitsuba properties
    mi_renderer.active_integrator = 'moment'
    bl_child_integrator_list = bl_moment_props.integrators
    for mi_integrator_props in mi_props_utils.named_references_with_class(mi_context, mi_props, 'Integrator'):
        bl_child_integrator_list.new(name=mi_integrator_props.id())
        bl_child_integrator = bl_child_integrator_list.collection[bl_child_integrator_list.count-1]
        if not apply_mi_integrator_properties(mi_context, mi_integrator_props, bl_child_integrator):
            return False
    # Cycles properties
    mi_context.log('Mitsuba Integrator "moment" is not supported in Blender Cycles', 'WARN')

    return True

_mi_integrator_properties_converters = {
    'path': apply_mi_path_properties,
    'moment': apply_mi_moment_properties,
}

def apply_mi_integrator_properties(mi_context, mi_props, bl_integrator_props=None):
    mi_integrator_type = mi_props.plugin_name()
    if mi_integrator_type not in _mi_integrator_properties_converters:
        mi_context.log(f'Mitsuba Integrator "{mi_integrator_type}" is not supported.', 'ERROR')
        return False
    
    return _mi_integrator_properties_converters[mi_integrator_type](mi_context, mi_props, bl_integrator_props)