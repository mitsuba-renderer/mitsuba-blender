import bpy

def apply_mi_independent_properties(mi_context, mi_props):
    mi_camera = mi_context.bl_scene.camera.data.mitsuba
    bl_renderer = mi_context.bl_scene.cycles
    bl_independent_props = getattr(mi_camera.samplers, 'independent', None)
    if bl_independent_props is None:
        mi_context.log(f'Mitsuba Sampler "independent" is not supported.', 'ERROR')
        return False
    # Mitsuba properties
    mi_camera.active_sampler = 'independent'
    bl_independent_props.sample_count = mi_props.get('sample_count', 4)
    bl_independent_props.seed = mi_props.get('seed', 0)
    # Cycles properties
    bl_renderer.sampling_pattern = 'SOBOL'
    bl_renderer.samples = mi_props.get('sample_count', 4)
    bl_renderer.preview_samples = mi_props.get('sample_count', 4)
    bl_renderer.seed = mi_props.get('seed', 0)
    return True

def apply_mi_stratified_properties(mi_context, mi_props):
    mi_camera = mi_context.bl_scene.camera.data.mitsuba
    bl_renderer = mi_context.bl_scene.cycles
    bl_stratified_props = getattr(mi_camera.samplers, 'stratified', None)
    if bl_stratified_props is None:
        mi_context.log(f'Mitsuba Sampler "stratified" is not supported.', 'ERROR')
        return False
    # Mitsuba properties
    mi_camera.active_sampler = 'stratified'
    bl_stratified_props.sample_count = mi_props.get('sample_count', 4)
    bl_stratified_props.seed = mi_props.get('seed', 0)
    bl_stratified_props.jitter = mi_props.get('jitter', True)
    # Cycles properties
    # NOTE: There isn't any equivalent sampler in Blender. We use the default Sobol pattern.
    bl_renderer.sampling_pattern = 'SOBOL'
    bl_renderer.samples = mi_props.get('sample_count', 4)
    bl_renderer.seed = mi_props.get('seed', 0)
    return True

def apply_mi_multijitter_properties(mi_context, mi_props):
    mi_camera = mi_context.bl_scene.camera.data.mitsuba
    bl_renderer = mi_context.bl_scene.cycles
    bl_multijitter_props = getattr(mi_camera.samplers, 'multijitter', None)
    if bl_multijitter_props is None:
        mi_context.log(f'Mitsuba Sampler "multijitter" is not supported.', 'ERROR')
        return False
    # Mitsuba properties
    mi_camera.active_sampler = 'multijitter'
    bl_multijitter_props.sample_count = mi_props.get('sample_count', 4)
    bl_multijitter_props.seed = mi_props.get('seed', 0)
    bl_multijitter_props.jitter = mi_props.get('jitter', True)
    # Cycles properties
    bl_renderer.sampling_pattern = 'CORRELATED_MUTI_JITTER' if bpy.app.version < (3, 0, 0) else 'PROGRESSIVE_MULTI_JITTER'
    bl_renderer.samples = mi_props.get('sample_count', 4)
    bl_renderer.seed = mi_props.get('seed', 0)
    return True

_mi_sampler_properties_converters = {
    'independent': apply_mi_independent_properties,
    'stratified': apply_mi_stratified_properties,
    'multijitter': apply_mi_multijitter_properties,
}

def apply_mi_sampler_properties(mi_context, mi_props):
    mi_sampler_type = mi_props.plugin_name()
    if mi_sampler_type not in _mi_sampler_properties_converters:
        mi_context.log(f'Mitsuba Sampler "{mi_sampler_type}" is not supported.', 'ERROR')
        return False
    
    return _mi_sampler_properties_converters[mi_sampler_type](mi_context, mi_props)
