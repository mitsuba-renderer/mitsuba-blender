from . import convert_float_texture_node

def export_combine_color_node(ctx, node):
    return {
        'type': 'combine_color',
        'mode' : node.mode,
        'red' :   convert_float_texture_node(ctx, node.inputs['Red']),
        'green' : convert_float_texture_node(ctx, node.inputs['Green']),
        'blue' :  convert_float_texture_node(ctx, node.inputs['Blue']),
    }