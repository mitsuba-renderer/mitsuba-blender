from . import convert_float_texture_node

def export_noise_texture_node(ctx, node):
    return {
        'type': 'noise',
        'noise_type' : node.noise_type,
        'dimensions' : node.noise_dimensions,
        'normalize' : node.normalize,
        'scale' :   convert_float_texture_node(ctx, node.inputs['Scale']),
        'detail' : convert_float_texture_node(ctx, node.inputs['Detail']),
        'roughness' :  convert_float_texture_node(ctx, node.inputs['Roughness']),
        'lacunarity' :  convert_float_texture_node(ctx, node.inputs['Lacunarity']),
        'distortion' :  convert_float_texture_node(ctx, node.inputs['Distortion']),
    }