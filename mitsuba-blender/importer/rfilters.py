import bpy

def apply_mi_tent_properties(mi_context, mi_props):
    mi_camera = mi_context.bl_scene.camera.data.mitsuba
    bl_box_props = getattr(mi_camera.rfilters, 'tent', None)
    if bl_box_props is None:
        mi_context.log(f'Mitsuba Reconstruction Filter "tent" is not supported.', 'ERROR')
        return False
    # Mitsuba properties
    mi_camera.active_rfilter = 'tent'
    # Cycles properties
    # NOTE: Cycles does not have any equivalent to the tent filter

    return True

def apply_mi_box_properties(mi_context, mi_props):
    mi_camera = mi_context.bl_scene.camera.data.mitsuba
    bl_renderer = mi_context.bl_scene.cycles
    bl_box_props = getattr(mi_camera.rfilters, 'box', None)
    if bl_box_props is None:
        mi_context.log(f'Mitsuba Reconstruction Filter "box" is not supported.', 'ERROR')
        return False
    # Mitsuba properties
    mi_camera.active_rfilter = 'box'
    # Cycles properties
    bl_renderer.pixel_filter_type = 'BOX'

    return True

def apply_mi_gaussian_properties(mi_context, mi_props):
    mi_camera = mi_context.bl_scene.camera.data.mitsuba
    bl_renderer = mi_context.bl_scene.cycles
    bl_box_props = getattr(mi_camera.rfilters, 'gaussian', None)
    if bl_box_props is None:
        mi_context.log(f'Mitsuba Reconstruction Filter "gaussian" is not supported.', 'ERROR')
        return False
    # Mitsuba properties
    mi_camera.active_rfilter = 'gaussian'
    bl_box_props.stddev = mi_props.get('stddev', 0.5)
    # Cycles properties
    bl_renderer.pixel_filter_type = 'GAUSSIAN'
    bl_renderer.filter_width = mi_props.get('stddev', 0.5)
    return True

_mi_rfilter_properties_converters = {
    'box': apply_mi_box_properties,
    'tent': apply_mi_tent_properties,
    'gaussian': apply_mi_gaussian_properties,
}

def apply_mi_rfilter_properties(mi_context, mi_props):
    mi_rfilter_type = mi_props.plugin_name()
    if mi_rfilter_type not in _mi_rfilter_properties_converters:
        mi_context.log(f'Mitsuba Reconstruction Filter "{mi_rfilter_type}" is not supported.', 'ERROR')
        return False
    
    return _mi_rfilter_properties_converters[mi_rfilter_type](mi_context, mi_props)
