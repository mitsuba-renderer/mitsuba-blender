import bpy
from . import convert_float_texture_node, convert_color_texture_node
from .. import logging

def export_mix_node(ctx, mix_node):
    mode = None
    if mix_node.blend_type == 'MIX':
        mode = 'blend'
    elif mix_node.blend_type == 'ADD':
        mode = 'add'
    elif mix_node.blend_type == 'SUBTRACT':
        mode = 'subtract'
    elif mix_node.blend_type == 'MULTIPLY':
        mode = 'multiply'
    elif mix_node.blend_type == 'DIFFERENCE':
        mode = 'difference'
    elif mix_node.blend_type == 'EXCLUSION':
        mode = 'exclusion'
    elif mix_node.blend_type == 'DARKEN':
        mode = 'darken'
    elif mix_node.blend_type == 'LIGHTEN':
        mode = 'lighten'
    elif mix_node.blend_type == 'OVERLAY':
        mode = 'overlay'
    elif mix_node.blend_type == 'SCREEN':
        mode = 'screen'
    else:
        raise NotImplementedError( "Mix color node type %s is not supported." % mix_node.blend_type)

    factor = convert_float_texture_node(ctx, mix_node.inputs[0])

    if isinstance(mix_node, bpy.types.ShaderNodeMixRGB):
        assert isinstance(mix_node.inputs[1], bpy.types.NodeSocketColor)
        assert isinstance(mix_node.inputs[2], bpy.types.NodeSocketColor)
        value_a = convert_color_texture_node(ctx, mix_node.inputs[1])
        value_b = convert_color_texture_node(ctx, mix_node.inputs[2])
    else:
        if mix_node.data_type == 'FLOAT':
            assert isinstance(mix_node.inputs[2], bpy.types.NodeSocketFloat)
            assert isinstance(mix_node.inputs[3], bpy.types.NodeSocketFloat)
            value_a = convert_color_texture_node(ctx, mix_node.inputs[2])
            value_b = convert_color_texture_node(ctx, mix_node.inputs[3])
        elif mix_node.data_type == 'RGBA':
            assert isinstance(mix_node.inputs[6], bpy.types.NodeSocketColor)
            assert isinstance(mix_node.inputs[7], bpy.types.NodeSocketColor)
            value_a = convert_color_texture_node(ctx, mix_node.inputs[6])
            value_b = convert_color_texture_node(ctx, mix_node.inputs[7])
        else:
            raise NotImplementedError( "Mix color node data type %s is not supported." % mix_node.data_type)

    params = {
        'type'  : 'mix_rgb',
        'mode'  : mode,
        'factor': factor,
        'color0': value_a,
        'color1': value_b,
    }

    return params