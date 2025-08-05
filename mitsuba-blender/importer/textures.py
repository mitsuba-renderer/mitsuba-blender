import bpy

from .. import logging
from . import bl_image_utils

######################
##    Converters    ##
######################

def mi_bitmap_to_bl_image(mi_context, mi_texture):
    filepath = mi_context.resolve_scene_relative_path(mi_texture.get('filename'))
    bl_image = bl_image_utils.load_bl_image_from_filepath(mi_context, filepath, mi_texture.get('raw', False))
    if bl_image is None:
        logging.error(f'Failed to load image from path "{filepath}".')
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
        logging.error(f'Mitsuba Texture type "{texture_type}" not supported.')
        return None

    # Create the Blender object
    bl_image = _texture_converters[texture_type](mi_context, mi_texture)

    return bl_image
