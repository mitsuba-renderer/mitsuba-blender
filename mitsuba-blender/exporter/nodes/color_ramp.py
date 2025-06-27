from . import convert_color_texture_node

def export_color_ramp_node(ctx, color_ramp_node):
    if color_ramp_node.color_ramp.color_mode != 'RGB':
        raise NotImplementedError("Type %s is not supported in ColorRamp. Only RGB mode are supported." % color_ramp_node.color_ramp.color_mode)

    params = {
        'type':  'color_ramp',
        'input': convert_color_texture_node(ctx, color_ramp_node.inputs['Fac']),
        'mode':  color_ramp_node.color_ramp.interpolation.lower()
    }

    color_bands = list(color_ramp_node.color_ramp.elements)
    params['num_bands'] = len(color_bands)
    for index in range(len(color_bands)):
        color_band_node = list(color_ramp_node.color_ramp.elements)[index]
        params['pos' + str(index)] = color_band_node.position
        params['color' + str(index)] = list(list(color_ramp_node.color_ramp.elements)[index].color)[:3]

    return params