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

# Integrators sharing the max_depth/rr_depth/hide_emitters parameter set
_mi_simple_integrators = ('path', 'volpath', 'volpathmis', 'ptracer')

def _mi_integrator_to_dict(mi_context, mi_props):
    '''Convert an integrator Properties tree to a plain dict literal.'''
    from mitsuba import Properties
    result = {'type': mi_props.plugin_name()}
    for name, value in mi_props.items():
        if isinstance(value, Properties.ResolvedReference):
            child_props = mi_context.mi_state.nodes[value.index()].props
            result[name] = _mi_integrator_to_dict(mi_context, child_props)
        elif isinstance(value, (bool, int, float, str)):
            result[name] = value
        else:
            raise ValueError(f'Integrator property "{name}" of type '
                             f'{type(value).__name__} cannot be stored as a dict literal.')
    return result

def apply_mi_integrator_properties(mi_context, mi_props):
    mi_integrator_type = mi_props.plugin_name()
    bl_renderer = mi_context.bl_scene.mitsuba

    if mi_integrator_type in _mi_simple_integrators:
        bl_props = getattr(bl_renderer.available_integrators, mi_integrator_type)
        bl_props.max_depth = mi_props.get('max_depth', -1)
        bl_props.rr_depth = mi_props.get('rr_depth', 5)
        bl_props.hide_emitters = mi_props.get('hide_emitters', False)
    elif mi_integrator_type == 'direct':
        bl_props = bl_renderer.available_integrators.direct
        shading_samples = mi_props.get('shading_samples', 1)
        bl_props.emitter_samples = mi_props.get('emitter_samples', shading_samples)
        bl_props.bsdf_samples = mi_props.get('bsdf_samples', shading_samples)
        bl_props.hide_emitters = mi_props.get('hide_emitters', False)
    else:
        # No UI representation: preserve the integrator verbatim through the
        # custom dict escape hatch so it survives an import/export round trip.
        try:
            integrator = _mi_integrator_to_dict(mi_context, mi_props)
        except ValueError:
            mi_context.log(f'Mitsuba Integrator "{mi_integrator_type}" is not supported.', 'ERROR')
            return False
        bl_renderer.custom_integrator = repr(integrator)
        mi_context.log(f'Mitsuba Integrator "{mi_integrator_type}" has no UI settings. '
                       'It was stored as a custom integrator dict.', 'WARN')
        return True
    bl_renderer.active_integrator = mi_integrator_type
    bl_renderer.custom_integrator = ''
    return True

##########################
##  RFilter properties  ##
##########################

def apply_mi_rfilter_properties(mi_context, mi_props):
    mi_rfilter_type = mi_props.plugin_name()
    mi_camera = mi_context.bl_scene.camera.data.mitsuba
    bl_props = getattr(mi_camera.rfilters, mi_rfilter_type, None)
    if bl_props is None:
        mi_context.log(f'Mitsuba Reconstruction Filter "{mi_rfilter_type}" is not supported.', 'ERROR')
        return False
    mi_camera.active_rfilter = mi_rfilter_type
    if mi_rfilter_type == 'gaussian':
        bl_props.stddev = mi_props.get('stddev', 0.5)
    elif mi_rfilter_type == 'mitchell':
        bl_props.B = mi_props.get('B', 1.0 / 3.0)
        bl_props.C = mi_props.get('C', 1.0 / 3.0)
    elif mi_rfilter_type == 'lanczos':
        bl_props.lobes = mi_props.get('lobes', 3)
    return True

##########################
##  Sampler properties  ##
##########################

def apply_mi_sampler_properties(mi_context, mi_props):
    mi_sampler_type = mi_props.plugin_name()
    mi_camera = mi_context.bl_scene.camera.data.mitsuba
    bl_props = getattr(mi_camera.samplers, mi_sampler_type, None)
    if bl_props is None:
        mi_context.log(f'Mitsuba Sampler "{mi_sampler_type}" is not supported.', 'ERROR')
        return False
    mi_camera.active_sampler = mi_sampler_type
    bl_props.sample_count = mi_props.get('sample_count', 4)
    bl_props.seed = mi_props.get('seed', 0)
    if mi_sampler_type in ('stratified', 'multijitter', 'orthogonal'):
        bl_props.jitter = mi_props.get('jitter', True)
    if mi_sampler_type == 'orthogonal':
        bl_props.strength = mi_props.get('strength', 2)
    return True

#######################
##  Film properties  ##
#######################

def apply_mi_hdrfilm_properties(mi_context, mi_props):
    mi_context.bl_scene.render.resolution_percentage = 100
    render_dims = (mi_props.get('width', 768), mi_props.get('height', 576))
    mi_context.bl_scene.render.resolution_x = render_dims[0]
    mi_context.bl_scene.render.resolution_y = render_dims[1]
    file_format = mi_fileformat_to_bl_fileformat(mi_context, mi_props.get('file_format', 'openexr'))
    if file_format is not None:
        mi_context.bl_scene.render.image_settings.file_format = file_format
    color_mode = mi_pixelformat_to_bl_pixelformat(mi_context, mi_props.get('pixel_format', 'rgba'))
    if color_mode is not None:
        mi_context.bl_scene.render.image_settings.color_mode = color_mode
    color_depth = mi_componentformat_to_bl_componentformat(mi_context, mi_props.get('component_format', 'float16'))
    if color_depth is not None:
        mi_context.bl_scene.render.image_settings.color_depth = color_depth

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

def init_mitsuba_variant(mi_context):
    '''Select the Mitsuba variant on the render properties. The importer
    never changes the active render engine.'''
    import mitsuba
    if not mi_context.import_render_settings:
        return True
    if 'scalar_rgb' not in mitsuba.variants():
        mi_context.log('Mitsuba variant "scalar_rgb" not available.', 'ERROR')
        return False
    mi_context.bl_scene.mitsuba.variant = 'scalar_rgb'
    return True
