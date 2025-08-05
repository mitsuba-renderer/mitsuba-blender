from . import convert_color_texture_node

def export_separate_rgb_node(ctx, node, parent_socket):
    input_texture = convert_color_texture_node(ctx, node.inputs[0])

    # Find the output channel linked to the parent socket
    channel_idx = 0
    for i, o in enumerate(node.outputs):
        for l in o.links:
            if l.to_socket == parent_socket:
                channel_idx = i
                break
    channel = ['r', 'g', 'b'][channel_idx]

    params = {
        'type'  : 'separate_rgb',
        'input' : input_texture,
        'channel': channel,
    }

    return params