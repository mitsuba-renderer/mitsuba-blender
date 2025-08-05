from . import convert_color_texture_node, convert_float_texture_node

def export_clamp_node(ctx, node):
    return {
        'type': 'clamp',
        'input' : convert_color_texture_node(ctx, node.inputs['Value']),
        'min': convert_float_texture_node(ctx, node.inputs['Min']),
        'max': convert_float_texture_node(ctx, node.inputs['Max']),
        'clamp_type': node.clamp_type,
    }