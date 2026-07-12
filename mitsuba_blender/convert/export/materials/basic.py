'''Converters for the basic Cycles BSDF nodes: Glossy, Glass, Refraction,
Transparent and Translucent.'''

import math

from . import node_converter
from ._eval import Constant, eval_color, eval_float, resolve

_DISTRIBUTIONS = {
    'BECKMANN': 'beckmann',
    'GGX': 'ggx',
    'ASHIKHMIN_SHIRLEY': 'beckmann',
    'MULTI_GGX': 'ggx',
}


def _constant_float(export_ctx, socket):
    '''Resolve a socket that must be a constant float. Textures and
    unsupported inputs fall back to the socket default with a warning.'''
    result = resolve(export_ctx, socket)
    if isinstance(result, Constant):
        return result.value
    reason = getattr(result, 'reason',
                     f'socket "{socket.name}" of node '
                     f'"{socket.node.name}" does not support textures')
    export_ctx.log(f'{reason}; using the default value', 'WARN')
    return float(socket.default_value)


def _eval_roughness(export_ctx, socket):
    '''Blender roughness -> Mitsuba alpha: constants are squared, texture
    dicts pass through unchanged.'''
    value = eval_float(export_ctx, socket)
    return value * value if isinstance(value, float) else value


@node_converter('BSDF_GLOSSY')
def convert_glossy(export_ctx, node):
    alpha = _eval_roughness(export_ctx, node.inputs['Roughness'])
    anisotropy = _constant_float(export_ctx, node.inputs['Anisotropy'])
    anisotropy = min(max(anisotropy, -0.99), 0.99)
    rotation = node.inputs['Rotation']
    if rotation.is_linked or rotation.default_value != 0.0:
        export_ctx.log(f'Glossy node "{node.name}": anisotropy rotation is '
                       'not supported; ignoring it.', 'WARN')

    if isinstance(alpha, float) and alpha == 0.0:
        params = {'type': 'conductor'}
    else:
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
                                                node.inputs['Color'])
    return {'type': 'twosided', 'bsdf': params}


def _convert_dielectric(export_ctx, node):
    ior = _constant_float(export_ctx, node.inputs['IOR'])
    alpha = _eval_roughness(export_ctx, node.inputs['Roughness'])
    if isinstance(alpha, float) and alpha == 0.0:
        params = {'type': 'thindielectric' if ior == 1.0 else 'dielectric'}
    else:
        params = {
            'type': 'roughdielectric',
            'alpha': alpha,
            'distribution': _DISTRIBUTIONS[node.distribution],
        }
    params['int_ior'] = ior
    params['specular_transmittance'] = eval_color(export_ctx,
                                                  node.inputs['Color'])
    return params


@node_converter('BSDF_GLASS')
def convert_glass(export_ctx, node):
    return _convert_dielectric(export_ctx, node)


@node_converter('BSDF_REFRACTION')
def convert_refraction(export_ctx, node):
    export_ctx.log(f'Mitsuba has no transmission-only BSDF; exporting '
                   f'Refraction node "{node.name}" as a dielectric that '
                   'also reflects.', 'WARN')
    return _convert_dielectric(export_ctx, node)


@node_converter('BSDF_TRANSPARENT')
def convert_transparent(export_ctx, node):
    result = resolve(export_ctx, node.inputs['Color'])
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
def convert_translucent(export_ctx, node):
    # Mitsuba has no standalone diffuse transmitter; principledthin with
    # full diffuse transmission is the closest match
    export_ctx.log(f'Approximating Translucent node "{node.name}" with a '
                   'thin principled BSDF.', 'WARN')
    return {
        'type': 'principledthin',
        'base_color': eval_color(export_ctx, node.inputs['Color']),
        'diff_trans': 2.0,
    }
