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
    # NOTE: We need to choose whether to keep the texture ID or the filename as Blender image name.
    #       This name will be used as the filename when exporting.
    # bl_image.name = mi_texture.id()
    return bl_image

def mi_checkerboard_to_bl_image(mi_context, mi_texture):
    # FIXME: Checkerboard textures do not need to reference a Blender image object.
    #        We therefore return a value other than None (which signifies failure) here 
    #        as no one should use the value returned by this function. 
    #        We need to find a better way of handling this.
    return False

######################
##   Main import    ##
######################

_texture_converters = {
    'bitmap': mi_bitmap_to_bl_image,
    'checkerboard': mi_checkerboard_to_bl_image,
}

def mi_texture_to_bl_image(mi_context, mi_texture):
    texture_type = mi_texture.plugin_name()
    if texture_type not in _texture_converters:
        mi_context.log(f'Mitsuba Texture type "{texture_type}" not supported.', 'ERROR')
        return None
    
    # Create the Blender object
    bl_image = _texture_converters[texture_type](mi_context, mi_texture)

    return bl_image
