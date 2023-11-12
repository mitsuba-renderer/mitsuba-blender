import bpy

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
    if mi_props.has_property('crop_offset_x') or mi_props.has_property('crop_offset_y') or mi_props.has_property('crop_width') or mi_props.has_property('crop_height'):
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
