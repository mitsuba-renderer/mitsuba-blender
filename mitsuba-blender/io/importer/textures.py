import os

if "bpy" in locals():
    import importlib
    if "bl_image_utils" in locals():
        importlib.reload(bl_image_utils)

import bpy

from . import bl_image_utils

######################
##    Converters    ##
######################

def mi_bitmap_to_bl_image(mi_context, mi_texture):
    filepath = mi_context.resolve_scene_relative_path(mi_texture.get('filename'))
    bl_image = bl_image_utils.load_bl_image_from_filepath(mi_context, filepath, mi_texture.get('raw', False))
    if bl_image is None:
        mi_context.log(f'Failed to load image from path "{filepath}".', 'ERROR')
        return None
    bl_image.name = mi_texture.id()
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
