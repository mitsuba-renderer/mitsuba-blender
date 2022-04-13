import os

import bpy

######################
##    Converters    ##
######################

def mi_bitmap_to_bl_image(mi_context, mi_texture):
    filename = mi_context.resolve_scene_relative_path(mi_texture.get('filename'))
    try:
        bl_image = bpy.data.images.load(filename)
    except:
        mi_context.log(f'Failed to load image "{filename}".', 'ERROR')
        return None
    bl_image.name = mi_texture.id()
    if mi_texture.get('raw', False):
        bl_image.colorspace_settings.is_data = True
        bl_image.colorspace_settings.name = 'Non-Color'
    return bl_image

######################
##   Main import    ##
######################

_texture_converters = {
    'bitmap': mi_bitmap_to_bl_image,
}

def mi_texture_to_bl_image(mi_context, mi_texture):
    texture_type = mi_texture.plugin_name()
    if texture_type not in _texture_converters:
        mi_context.log(f'Mitsuba Texture type "{texture_type}" not supported.', 'ERROR')
        return None
    
    # Create the Blender object
    bl_image = _texture_converters[texture_type](mi_context, mi_texture)

    return bl_image
