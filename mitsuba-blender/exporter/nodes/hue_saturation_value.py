from . import convert_color_texture_node, convert_float_texture_node

def export_hue_saturation_value_node(ctx, node):
    return {
        'type': 'hue_saturation_value',
        'input' : convert_color_texture_node(ctx, node.inputs['Color']),
        'hue': convert_float_texture_node(ctx, node.inputs['Hue']),
        'saturation': convert_float_texture_node(ctx, node.inputs['Saturation']),
        'value': convert_float_texture_node(ctx, node.inputs['Value']),
        'mix': convert_float_texture_node(ctx, node.inputs['Fac']),
    }