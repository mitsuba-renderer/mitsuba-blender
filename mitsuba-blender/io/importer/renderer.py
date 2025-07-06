if "bpy" in locals():
    import importlib
    if "mi_props_utils" in locals():
        importlib.reload(mi_props_utils)

import bpy

from . import mi_props_utils

#################
##  Utilities  ##
#################

_fileformat_values = {
    'openexr': 'OPEN_EXR',
    'exr': 'OPEN_EXR',
    # FIXME: Support other file formats
}

def mi_fileformat_to_bl_fileformat(mi_context, mi_file_format):
    if mi_file_format not in _fileformat_values:
        mi_context.log(f'Mitsuba Film image file format "{mi_file_format}" is not supported.', 'ERROR')
        return None
    return _fileformat_values[mi_file_format]

_pixelformat_values = {
    'rgb': 'RGB',
    'rgba': 'RGBA',
    # FIXME: Support other pixel formats
}

def mi_pixelformat_to_bl_pixelformat(mi_context, mi_pixel_format):
    if mi_pixel_format not in _pixelformat_values:
        mi_context.log(f'Mitsuba Film image pixel format "{mi_pixel_format}" is not supported.', 'ERROR')
        return None
    return _pixelformat_values[mi_pixel_format]

_componentformat_values = {
    'float16': '16',
    'float32': '32',
    # FIXME: Support other component formats
}

def mi_componentformat_to_bl_componentformat(mi_context, mi_component_format):
    if mi_component_format not in _componentformat_values:
        mi_context.log(f'Mitsuba Film image component format "{mi_component_format}" is not supported.', 'ERROR')
        return None
    return _componentformat_values[mi_component_format]

#############################
##  Integrator properties  ##
#############################

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

##########################
##  RFilter properties  ##
##########################

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

##########################
##  Sampler properties  ##
##########################

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
    if bpy.app.version < (3, 5, 0):
        bl_renderer.sampling_pattern = 'SOBOL'
    elif bpy.app.version < (4, 0, 0):
        bl_renderer.sampling_pattern = 'SOBOL_BURLEY'
    else:
        bl_renderer.sampling_pattern = 'AUTOMATIC'
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
    if bpy.app.version < (3, 5, 0):
        bl_renderer.sampling_pattern = 'SOBOL'
    elif bpy.app.version < (4, 0, 0):
        bl_renderer.sampling_pattern = 'SOBOL_BURLEY'
    else:
        bl_renderer.sampling_pattern = 'AUTOMATIC'
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
    if bpy.app.version < (3, 0, 0):
        bl_renderer.sampling_pattern = 'CORRELATED_MUTI_JITTER'
    elif bpy.app.version < (3, 5, 0):
        bl_renderer.sampling_pattern = 'PROGRESSIVE_MULTI_JITTER'
    else:
        bl_renderer.sampling_pattern = 'TABULATED_SOBOL'
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

#######################
##  Film properties  ##
#######################

def apply_mi_hdrfilm_properties(mi_context, mi_props):
    mi_context.bl_scene.render.resolution_percentage = 100
    render_dims = (mi_props.get('width', 768), mi_props.get('height', 576))
    mi_context.bl_scene.render.resolution_x = render_dims[0]
    mi_context.bl_scene.render.resolution_y = render_dims[1]
    mi_context.bl_scene.render.image_settings.file_format = mi_fileformat_to_bl_fileformat(mi_context, mi_props.get('file_format', 'openexr'))
    mi_context.bl_scene.render.image_settings.color_mode = mi_pixelformat_to_bl_pixelformat(mi_context, mi_props.get('pixel_format', 'rgba'))
    mi_context.bl_scene.render.image_settings.color_depth = mi_componentformat_to_bl_componentformat(mi_context, mi_props.get('component_format', 'float16'))

    crop_keys = ['crop_offset_x', 'crop_offset_y', 'crop_width', 'crop_height']
    if any(key in mi_props for key in crop_keys):
        mi_context.bl_scene.render.use_border = True
        # FIXME: Do we want to crop the resulting image ?
        mi_context.bl_scene.render.use_crop_to_border = True
        offset_x = mi_props.get('crop_offset_x', 0)
        offset_y = mi_props.get('crop_offset_y', 0)
        width = mi_props.get('crop_width', render_dims[0])
        height = mi_props.get('crop_height', render_dims[1])
        mi_context.bl_scene.render.border_min_x = offset_x / render_dims[0]
        mi_context.bl_scene.render.border_max_x = (offset_x + width) / render_dims[0]
        mi_context.bl_scene.render.border_min_y = offset_y / render_dims[1]
        mi_context.bl_scene.render.border_max_y = (offset_y + height) / render_dims[1]
    return True

_mi_film_properties_converters = {
    'hdrfilm': apply_mi_hdrfilm_properties
}

def apply_mi_film_properties(mi_context, mi_props):
    mi_film_type = mi_props.plugin_name()
    if mi_film_type not in _mi_film_properties_converters:
        mi_context.log(f'Mitsuba Film "{mi_film_type}" is not supported.', 'ERROR')
        return False
    
    return _mi_film_properties_converters[mi_film_type](mi_context, mi_props)

###########################
##  Renderer properties  ##
###########################

def init_mitsuba_renderer(mi_context):
    mi_context.bl_scene.render.engine = 'MITSUBA'
    mi_renderer = mi_context.bl_scene.mitsuba
    if 'scalar_rgb' not in mi_renderer.variants():
        mi_context.log('Mitsuba variant "scalar_rgb" not available.', 'ERROR')
        return False
    mi_renderer.variant = 'scalar_rgb'
    return True
