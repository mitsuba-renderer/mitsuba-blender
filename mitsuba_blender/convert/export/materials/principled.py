'''Converter for the Principled BSDF shader node.

The core parameters map onto Mitsuba's principled BSDF. Emission becomes a
separate area emitter dict, an Alpha below one wraps the BSDF in a mask,
and the Normal input wraps it in normalmap/bumpmap adapters.
'''

from . import node_converter
from ._resolve import Constant, Texture, Unsupported, eval_color, eval_float, resolve, scalar_from_socket
from .textures import convert_normal_input


def _spec_tint(export_ctx, ref):
    '''Blender tints the specular highlight with a color (white means
    untinted) while Mitsuba blends from white toward the base color hue,
    so the distance from white becomes the tint amount.'''
    node = ref.node
    socket = node.inputs['Specular Tint']
    result = resolve(export_ctx, socket, stack=ref.stack)
    if isinstance(result, Constant):
        return 1.0 - min(result.value[:3])
    export_ctx.log(f'Specular Tint of node "{node.name}" only supports '
                   'constant colors; using the default value', 'WARN')
    return 0.0


def _emitter(export_ctx, ref):
    '''Build an area emitter dict from the emission inputs, or None.'''
    node = ref.node
    strength = scalar_from_socket(export_ctx, node.inputs['Emission Strength'],
                               ref.stack)
    if strength <= 0.0:
        return None
    result = resolve(export_ctx, node.inputs['Emission Color'],
                     stack=ref.stack)
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


@node_converter('BSDF_PRINCIPLED')
def convert_principled(export_ctx, ref):
    node = ref.node
    stack = ref.stack
    params = {
        'type': 'principled',
        'base_color': eval_color(export_ctx, node.inputs['Base Color'],
                                 stack=stack),
        'roughness': eval_float(export_ctx, node.inputs['Roughness'],
                                stack=stack),
        'metallic': eval_float(export_ctx, node.inputs['Metallic'],
                               stack=stack),
        'anisotropic': eval_float(export_ctx, node.inputs['Anisotropic'],
                                  stack=stack),
        'spec_tint': _spec_tint(export_ctx, ref),
        'spec_trans': eval_float(export_ctx,
                                 node.inputs['Transmission Weight'],
                                 stack=stack),
        'sheen': eval_float(export_ctx, node.inputs['Sheen Weight'],
                            stack=stack),
        'sheen_tint': eval_float(export_ctx, node.inputs['Sheen Tint'],
                                 stack=stack),
        'clearcoat': eval_float(export_ctx, node.inputs['Coat Weight'],
                                stack=stack),
        'clearcoat_gloss':
            1.0 - scalar_from_socket(export_ctx, node.inputs['Coat Roughness'],
                                  stack),
    }

    spec_trans = params['spec_trans']
    if isinstance(spec_trans, dict) or spec_trans > 0.0:
        # Blender drives transmission with the IOR input; Mitsuba shares a
        # single eta between reflection and refraction. Transmissive
        # materials must stay one-sided.
        ior = scalar_from_socket(export_ctx, node.inputs['IOR'], stack)
        params['eta'] = max(ior, 1.0 + 1e-3)
        bsdf = params
    else:
        specular = scalar_from_socket(export_ctx,
                                   node.inputs['Specular IOR Level'], stack)
        params['specular'] = max(specular, 1e-3)
        bsdf = {'type': 'twosided', 'bsdf': params}

    bsdf = convert_normal_input(export_ctx, node.inputs['Normal'], bsdf, stack)

    alpha = eval_float(export_ctx, node.inputs['Alpha'], stack=stack)
    if isinstance(alpha, dict) or alpha < 1.0:
        bsdf = {'type': 'mask', 'opacity': alpha, 'bsdf': bsdf}

    return {'bsdf': bsdf, 'emitter': _emitter(export_ctx, ref)}
