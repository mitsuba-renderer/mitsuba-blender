from . import convert_color_texture_node, convert_float_texture_node

def export_map_range_node(ctx, node):
    return {
        'type': 'map_range',
        'input' : convert_color_texture_node(ctx, node.inputs['Value']),
        'from_min': convert_float_texture_node(ctx, node.inputs['From Min']),
        'from_max': convert_float_texture_node(ctx, node.inputs['From Max']),
        'to_min': convert_float_texture_node(ctx, node.inputs['To Min']),
        'to_max': convert_float_texture_node(ctx, node.inputs['To Max']),
        'clamp': node.clamp,
        'interpolation_type': node.interpolation_type,
    }