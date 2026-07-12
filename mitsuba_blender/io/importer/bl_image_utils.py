import bpy

def load_bl_image_from_filepath(mi_context, filepath, is_data):
    try:
        bl_image = bpy.data.images.load(filepath)
        if is_data:
            bl_image.colorspace_settings.is_data = True
            bl_image.colorspace_settings.name = 'Non-Color'
        return bl_image
    except:
        mi_context.log(f'Failed to load image "{filepath}".', 'ERROR')
        return None
