from . import convert_color_texture_node

def export_math_node(ctx, node):
    if node.operation == 'ADD':
        mode = 'add'
    elif node.operation == 'SUBTRACT':
        mode = 'subtract'
    elif node.operation == 'MULTIPLY':
        mode = 'multiply'
    else:
        raise NotImplementedError("Math node operation %s is not supported! Only "
                                  "'add', 'multiply' and 'substract' are currently"
                                  "supported." % node.operation)

    if (len(node.inputs[0].links) < 1):
        if node.inputs[0].default_value < 0.0:
            node.inputs[0].default_value  = 0.001
    if (len(node.inputs[1].links) < 1):
        if node.inputs[1].default_value < 0.0:
            node.inputs[1].default_value  = 0.001

    color0 = convert_color_texture_node(ctx, node.inputs[0])
    color1 = convert_color_texture_node(ctx, node.inputs[1])

    params = {
        'type'  : 'mix_rgb',
        'mode'  : mode,
        'factor': 1.0,
        'color0': color0,
        'color1': color1,
    }

    return params
