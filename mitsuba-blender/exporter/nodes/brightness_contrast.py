from . import convert_color_texture_node, convert_float_texture_node

def export_brightness_contrast_node(ctx, node):
    return {
        'type'          : 'brightness_contrast',
        'color'         : convert_color_texture_node(ctx, node.inputs['Color']),
        'brightness'    : convert_float_texture_node(ctx, node.inputs['Bright']),
        'contrast'      : convert_float_texture_node(ctx, node.inputs['Contrast'])
    }