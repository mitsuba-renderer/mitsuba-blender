'''Converter for the Principled BSDF shader node.

The core parameters map onto Mitsuba's principled BSDF. Emission becomes a
separate area emitter dict, an Alpha below one wraps the BSDF in a mask,
and a tangent-space Normal Map input wraps it in a normalmap adapter.
'''

from . import node_converter
from ._eval import Constant, Texture, Unsupported, eval_color, eval_float, \
    resolve, trace_source


def _constant_float(export_ctx, socket):
    '''Resolve a socket that Mitsuba only accepts as a constant float.'''
    result = resolve(export_ctx, socket)
    if isinstance(result, Constant):
        return result.value
    if isinstance(result, Unsupported):
        reason = result.reason
    else:
        reason = (f'socket "{socket.name}" of node "{socket.node.name}" '
                  'only supports constant values')
    export_ctx.log(f'{reason}; using the default value', 'WARN')
    return float(socket.default_value)


def _spec_tint(export_ctx, node):
    '''Blender tints the specular highlight with a color (white means
    untinted) while Mitsuba blends from white toward the base color hue,
    so the distance from white becomes the tint amount.'''
    socket = node.inputs['Specular Tint']
    result = resolve(export_ctx, socket)
    if isinstance(result, Constant):
        return 1.0 - min(result.value[:3])
    export_ctx.log(f'Specular Tint of node "{node.name}" only supports '
                   'constant colors; using the default value', 'WARN')
    return 0.0


def _emitter(export_ctx, node):
    '''Build an area emitter dict from the emission inputs, or None.'''
    strength = _constant_float(export_ctx, node.inputs['Emission Strength'])
    if strength <= 0.0:
        return None
    result = resolve(export_ctx, node.inputs['Emission Color'])
    if isinstance(result, Texture):
        if strength != 1.0:
            export_ctx.log(f'Cannot scale the textured emission color of '
                           f'node "{node.name}" by the emission strength; '
                           'exporting the texture unscaled', 'WARN')
        return {'type': 'area', 'radiance': result.params}
    if isinstance(result, Unsupported):
        export_ctx.log(f'{result.reason}; ignoring the emission of node '
                       f'"{node.name}"', 'WARN')
        return None
    radiance = [c * strength for c in result.value[:3]]
    if max(radiance) == 0.0:
        return None
    return {'type': 'area', 'radiance': export_ctx.spectrum(radiance)}


def _normal_texture(export_ctx, node):
    '''The Mitsuba texture feeding a tangent-space Normal Map node on the
    Normal input, or None.'''
    source, _ = trace_source(node.inputs['Normal'])
    if source is None:
        return None
    if source.type != 'NORMAL_MAP' or source.space != 'TANGENT':
        export_ctx.log(f'Only tangent-space Normal Map nodes are supported '
                       f'on the Normal input of node "{node.name}"; '
                       'ignoring it', 'WARN')
        return None
    strength = _constant_float(export_ctx, source.inputs['Strength'])
    if strength != 1.0:
        export_ctx.log(f'Mitsuba does not support the strength of Normal '
                       f'Map node "{source.name}"; using the map at full '
                       'strength', 'WARN')
    result = resolve(export_ctx, source.inputs['Color'])
    if isinstance(result, Texture):
        return result.params
    export_ctx.log(f'The Color input of Normal Map node "{source.name}" '
                   'must be a texture; ignoring the normal map', 'WARN')
    return None


@node_converter('BSDF_PRINCIPLED')
def convert_principled(export_ctx, node):
    params = {
        'type': 'principled',
        'base_color': eval_color(export_ctx, node.inputs['Base Color']),
        'roughness': eval_float(export_ctx, node.inputs['Roughness']),
        'metallic': eval_float(export_ctx, node.inputs['Metallic']),
        'anisotropic': eval_float(export_ctx, node.inputs['Anisotropic']),
        'spec_tint': _spec_tint(export_ctx, node),
        'spec_trans': eval_float(export_ctx,
                                 node.inputs['Transmission Weight']),
        'sheen': eval_float(export_ctx, node.inputs['Sheen Weight']),
        'sheen_tint': eval_float(export_ctx, node.inputs['Sheen Tint']),
        'clearcoat': eval_float(export_ctx, node.inputs['Coat Weight']),
        'clearcoat_gloss':
            1.0 - _constant_float(export_ctx, node.inputs['Coat Roughness']),
    }

    spec_trans = params['spec_trans']
    if isinstance(spec_trans, dict) or spec_trans > 0.0:
        # Blender drives transmission with the IOR input; Mitsuba shares a
        # single eta between reflection and refraction. Transmissive
        # materials must stay one-sided.
        ior = _constant_float(export_ctx, node.inputs['IOR'])
        params['eta'] = max(ior, 1.0 + 1e-3)
        bsdf = params
    else:
        specular = _constant_float(export_ctx,
                                   node.inputs['Specular IOR Level'])
        params['specular'] = max(specular, 1e-3)
        bsdf = {'type': 'twosided', 'bsdf': params}

    normal = _normal_texture(export_ctx, node)
    if normal is not None:
        bsdf = {'type': 'normalmap', 'normalmap': normal, 'bsdf': bsdf}

    alpha = eval_float(export_ctx, node.inputs['Alpha'])
    if isinstance(alpha, dict) or alpha < 1.0:
        bsdf = {'type': 'mask', 'opacity': alpha, 'bsdf': bsdf}

    return {'bsdf': bsdf, 'emitter': _emitter(export_ctx, node)}
