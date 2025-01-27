from ... import logging
import bpy

def next_node_upstream(ctx, socket):
    node = socket.links[0].from_node
    while node.type == 'REROUTE':
        node = node.inputs[0].links[0].from_node

    # Entering a group
    if node.type == 'GROUP':
        ctx.node_groups.append(node)
        socket_name = socket.links[0].from_socket.name
        node = next_node_upstream(ctx, node.node_tree.nodes['Group Output'].inputs[socket_name])

    return node

def convert_float_texture_node(ctx, socket):
    from .color_ramp import export_color_ramp_node
    from .mix import export_mix_node
    from .math import export_math_node
    from .separate_rgb import export_separate_rgb_node
    from .texture import export_texture_node
    from .hue_saturation_value import export_hue_saturation_value_node
    from .map_range import export_map_range_node
    from .clamp import export_clamp_node
    from .rgb_to_bw import export_rgb_to_bw_node
    from .combine_color import export_combine_color_node
    from .noise_texture import export_noise_texture_node

    params = None

    if socket.is_linked:
        node = next_node_upstream(ctx, socket)

        if node.type == "TEX_IMAGE":
            params = export_texture_node(ctx, node)
        elif node.type == "VALTORGB":
            params = export_color_ramp_node(ctx, node)
        elif node.type == "MAP_RANGE":
            params = export_map_range_node(ctx, node)
        elif node.type == "CLAMP":
            params = export_clamp_node(ctx, node)
        elif node.type == "RGBTOBW":
            params = export_rgb_to_bw_node(ctx, node)
        elif node.type == "COMBINE_COLOR":
            params = export_combine_color_node(ctx, node)
        elif node.type == "TEX_NOISE":
            params = export_noise_texture_node(ctx, node)
        elif node.type == "HUE_SAT":
            params = export_hue_saturation_value_node(ctx, node)
        elif node.type == 'BRIGHTCONTRAST':
            params = convert_color_texture_node(ctx, node.inputs['Color'])
        elif node.type == 'MIX':
            params = export_mix_node(ctx, node)
        elif node.type == 'MIX_RGB':
            params = export_mix_node(ctx, node)
        elif node.type == 'MATH':
            params = export_math_node(ctx, node)
        elif node.type == 'SEPARATE_COLOR':
            params = export_separate_rgb_node(ctx, node, socket)
        elif node.type == 'GROUP_INPUT':
            for group in ctx.node_groups:
                for node2 in group.node_tree.nodes:
                    if node2 == node:
                        socket_name = socket.links[0].from_socket.name
                        socket_group = group.inputs[socket_name]
                        return convert_float_texture_node(ctx, socket_group)
        else:
            raise NotImplementedError( "Node type %s is not supported. Only texture nodes are supported for float inputs" % node.type)
    else:
        if socket.name == 'Roughness': #roughness values in blender are remapped with a square root
            params = pow(socket.default_value, 2)
            if socket.default_value < 0.0:
                params: 0.001
        if socket.name == 'Normal':
            params = None
        else:
            params = socket.default_value

            # Convert bpy_float[4] -> bpy_float[3]
            if hasattr(params, '__len__') and len(params) == 4:
                params = list(params[:3])

    return params

def convert_color_texture_node(ctx, socket):
    from .color_ramp import export_color_ramp_node
    from .mix import export_mix_node
    from .math import export_math_node
    from .separate_rgb import export_separate_rgb_node
    from .texture import export_texture_node
    from .hue_saturation_value import export_hue_saturation_value_node
    from .map_range import export_map_range_node
    from .clamp import export_clamp_node
    from .rgb_to_bw import export_rgb_to_bw_node
    from .combine_color import export_combine_color_node
    from .noise_texture import export_noise_texture_node

    params = None

    if socket.is_linked:
        node = next_node_upstream(ctx, socket)
        if node.type == "TEX_IMAGE":
            params = export_texture_node(ctx, node)
        elif node.type == "RGB":
            base_color = list(node.outputs['Color'].default_value)
            params = ctx.spectrum(base_color[:3])
        elif node.type == "VERTEX_COLOR":
            params = {
                'type': 'mesh_attribute',
                'name': 'vertex_%s' % node.layer_name
            }
        elif node.type == "MAP_RANGE":
            params = export_map_range_node(ctx, node)
        elif node.type == "CLAMP":
            params = export_clamp_node(ctx, node)
        elif node.type == "RGBTOBW":
            params = export_rgb_to_bw_node(ctx, node)
        elif node.type == "COMBINE_COLOR":
            params = export_combine_color_node(ctx, node)
        elif node.type == "HUE_SAT":
            params = export_hue_saturation_value_node(ctx, node)
        elif node.type == "TEX_NOISE":
            params = export_noise_texture_node(ctx, node)
        elif node.type == "VALTORGB":
            params = export_color_ramp_node(ctx, node)
        elif node.type == 'CURVE_RGB': # TODO: implement curve_rgb in mitsuba
            logging.warn('CURVE_RGB node is not implemented! Falling back to input color signal.')
            params = convert_color_texture_node(ctx, node.inputs['Color'])
        elif node.type == 'MIX':
            params = export_mix_node(ctx, node)
        elif node.type == 'MIX_RGB':
            params = export_mix_node(ctx, node)
        elif node.type == 'MATH':
            params = export_math_node(ctx, node)
        elif node.type == 'SEPARATE_COLOR':
            params = export_separate_rgb_node(ctx, node, socket)
        elif node.type == 'GROUP_INPUT':
            for group in ctx.node_groups: # TODO find a more efficient way
                for node2 in group.node_tree.nodes:
                    if node2 == node:
                        socket_name = socket.links[0].from_socket.name
                        socket_group = group.inputs[socket_name]
                        return convert_color_texture_node(ctx, socket_group)
        else:
            raise NotImplementedError("Node type %s is not supported" % node.type)
    else:
        params = ctx.spectrum(socket.default_value)

    return params

# Should exclusively be input to BSDF nodes
def convert_normal_map_node(ctx, socket):
    params = None

    meta = {
        'is_bump' : False,
        'strength': 1.0,
        'distance': 1.0
    }

    if socket.is_linked:
        node = next_node_upstream(ctx, socket)

        if node.type == 'NORMAL_MAP':
            with ctx.scope_raw_texture_input():
                params = convert_color_texture_node(ctx, node.inputs['Color'])
            strength = convert_float_texture_node(ctx, node.inputs['Strength'])
            if not isinstance(strength, float):
                logging.warn("Warning: A normal map with spatially varying strength is not supported in Mitsuba. Ignoring strength parameter.")
            else:
                if strength != 1.0:
                    if 'gain' in params:
                        params['gain'] = strength
                    else:
                        logging.warn(f"normalmap: gain cannot be applied on texture type: {params['type']}")
        elif node.type == 'BUMP':
            with ctx.scope_raw_texture_input():
                params = convert_color_texture_node(ctx, node.inputs['Height'])
            strength = convert_float_texture_node(ctx, node.inputs['Strength'])
            if not isinstance(strength, float):
                logging.warn("Warning: A bump map with spatially varying strength is not supported in Mitsuba. Ignoring strength parameter.")
            else:
                if strength != 1.0:
                    if 'gain' in params:
                        params['gain'] = strength
                    else:
                        logging.warn(f"normalmap: gain cannot be applied on texture type: {params['type']}")
            meta['is_bump'] = True
            meta['distance'] = convert_float_texture_node(ctx, node.inputs['Distance'])
        else:
            params = convert_color_texture_node(ctx, socket)
    else:
        params = None

    return params, meta
