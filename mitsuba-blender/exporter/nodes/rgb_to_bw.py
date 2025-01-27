from . import convert_color_texture_node

def export_rgb_to_bw_node(ctx, node):
    return {
        'type': 'rgb_to_bw',
        'color' : convert_color_texture_node(ctx, node.inputs['Color']),
    }