'''Converters for the basic Cycles BSDF nodes: Diffuse, Glossy, Glass,
Refraction, Transparent and Translucent.'''

import math

from . import node_converter
from ._resolve import Constant, eval_color, eval_float, resolve, scalar_from_socket
from .textures import convert_normal_input

# Mapping from MULTI_GGX is an approximation which diverges with high roughness
_DISTRIBUTIONS = {
    'BECKMANN': 'beckmann',
    'GGX': 'ggx',
    'ASHIKHMIN_SHIRLEY': 'beckmann',
    'MULTI_GGX': 'ggx',
}
_HANDLED_DISTRIBUTION = ('BECKMANN', 'GGX')


def _eval_roughness(export_ctx, socket, stack):
    '''Blender roughness -> Mitsuba alpha. Cycles has used the square root
    of the internal roughness as the UI value since 2.8, so the socket
    value is squared; roughconductor and friends take alpha directly.
    '''
    value = eval_float(export_ctx, socket, stack=stack)
    if isinstance(value, dict):
        return {
                'type': 'math',
                'op' : 'POWER',
                'use_clamp' : False,
                'a': value,
                'b': 2.0
                }
    return value * value


@node_converter('BSDF_DIFFUSE')
def convert_diffuse(export_ctx, ref):
    node = ref.node
    roughness = node.inputs['Roughness']
    if roughness.is_linked or roughness.default_value > 0.0:
        export_ctx.log(f'Mitsuba has no rough diffuse BSDF; ignoring the '
                       f'roughness of node "{node.name}".', 'WARN')
    bsdf = {
        'type': 'twosided',
        'bsdf': {
            'type': 'diffuse',
            'reflectance': eval_color(export_ctx, node.inputs['Color'], stack=ref.stack),
        },
    }
    return convert_normal_input(export_ctx, node.inputs['Normal'], bsdf, stack=ref.stack)


@node_converter('BSDF_GLOSSY')
def convert_glossy(export_ctx, ref):
    node = ref.node
    alpha = _eval_roughness(export_ctx, node.inputs['Roughness'], stack=ref.stack)
    anisotropy = scalar_from_socket(export_ctx, node.inputs['Anisotropy'], stack=ref.stack)
    anisotropy = min(max(anisotropy, -0.99), 0.99)
    rotation = node.inputs['Rotation']
    if rotation.is_linked or rotation.default_value != 0.0:
        export_ctx.log(f'Glossy node "{node.name}": anisotropy rotation is '
                       'not supported; ignoring it.', 'WARN')

    if isinstance(alpha, float) and alpha == 0.0:
        params = {'type': 'conductor'}
    else:
        if node.distribution not in _HANDLED_DISTRIBUTION:
            export_ctx.log(
                f'Approximating distribution "{node.distribution}" with "{_DISTRIBUTIONS[node.distribution]}".',
                'WARN')

        params = {
            'type': 'roughconductor',
            'distribution': _DISTRIBUTIONS[node.distribution],
        }
        if abs(anisotropy) < 1e-4:
            params['alpha'] = alpha
        elif not isinstance(alpha, float):
            export_ctx.log(f'Glossy node "{node.name}": anisotropy is not '
                           'supported with a textured roughness; ignoring '
                           'it.', 'WARN')
            params['alpha'] = alpha
        else:
            # Cycles' anisotropy mapping: the aspect ratio stretches alpha
            # along the tangent, a negative value swaps the axes
            aspect = math.sqrt(1.0 - 0.9 * abs(anisotropy))
            alpha_u, alpha_v = alpha / aspect, alpha * aspect
            if anisotropy < 0.0:
                alpha_u, alpha_v = alpha_v, alpha_u
            params['alpha_u'] = alpha_u
            params['alpha_v'] = alpha_v
    params['specular_reflectance'] = eval_color(export_ctx,
                                                node.inputs['Color'],
                                                stack=ref.stack)
    return convert_normal_input(export_ctx, node.inputs['Normal'],
                                {'type': 'twosided', 'bsdf': params}, stack=ref.stack)


def _convert_dielectric(export_ctx, ref):
    node = ref.node
    ior = scalar_from_socket(export_ctx, node.inputs['IOR'], stack=ref.stack)
    alpha = _eval_roughness(export_ctx, node.inputs['Roughness'], stack=ref.stack)
    if isinstance(alpha, float) and alpha == 0.0:
        params = {'type': 'thindielectric' if ior == 1.0 else 'dielectric'}
    else:
        if node.distribution not in _HANDLED_DISTRIBUTION:
            export_ctx.log(
                f'Approximating distribution "{node.distribution}" with "{_DISTRIBUTIONS[node.distribution]}".',
                'WARN')

        params = {
            'type': 'roughdielectric',
            'alpha': alpha,
            'distribution': _DISTRIBUTIONS[node.distribution],
        }
    params['int_ior'] = ior
    params['specular_transmittance'] = eval_color(export_ctx,
                                                  node.inputs['Color'], stack=ref.stack)
    return convert_normal_input(export_ctx, node.inputs['Normal'], params, stack=ref.stack)


@node_converter('BSDF_GLASS')
def convert_glass(export_ctx, ref):
    return _convert_dielectric(export_ctx, ref)


@node_converter('BSDF_REFRACTION')
def convert_refraction(export_ctx, ref):
    export_ctx.log(f'Mitsuba has no transmission-only BSDF; exporting '
                   f'Refraction node "{ref.node.name}" as a dielectric that '
                   'also reflects.', 'WARN')
    return _convert_dielectric(export_ctx, ref)


@node_converter('BSDF_TRANSPARENT')
def convert_transparent(export_ctx, ref):
    node = ref.node
    result = resolve(export_ctx, node.inputs['Color'], stack=ref.stack)
    if isinstance(result, Constant):
        color = result.value[:3]
    else:
        export_ctx.log(f'Transparent node "{node.name}": only constant '
                       'colors are supported; using the socket value. '
                       'Consider using a Mix Shader instead.', 'WARN')
        color = tuple(node.inputs['Color'].default_value)[:3]
    if min(color) == 1.0:
        return {'type': 'null'}
    # A tinted transparent BSDF transmits `color` and absorbs the rest: a
    # mask over a black diffuse with the inverted color as opacity
    return {
        'type': 'mask',
        'opacity': export_ctx.spectrum([1.0 - x for x in color]),
        'bsdf': {
            'type': 'diffuse',
            'reflectance': export_ctx.spectrum(0.0),
        },
    }


@node_converter('BSDF_TRANSLUCENT')
def convert_translucent(export_ctx, ref):
    # Mitsuba has no standalone diffuse transmitter; principledthin with
    # full diffuse transmission is the closest match
    node = ref.node
    export_ctx.log(f'Approximating Translucent node "{node.name}" with a '
                   'thin principled BSDF.', 'WARN')
    bsdf = {
        'type': 'principledthin',
        'base_color': eval_color(export_ctx, node.inputs['Color'], stack=ref.stack),
        'diff_trans': 2.0,
    }
    return convert_normal_input(export_ctx, node.inputs['Normal'], bsdf, stack=ref.stack)
