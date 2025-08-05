from . import convert_color_texture_node, convert_float_texture_node

def export_invert_node(ctx, node):
    return {
        'type'  : 'invert',
        'color' : convert_color_texture_node(ctx, node.inputs['Color']),
        'fac'   : convert_float_texture_node(ctx, node.inputs['Fac'])
    }