'''Converters for the shader combinator nodes: Mix Shader, Add Shader,
Emission and Holdout.'''

from ... import ConversionError
from . import convert_shader_node, node_converter
from .textures import _math
from ._resolve import Constant, NodeRef, Texture, resolve, eval_float, trace_source, scalar_from_socket


def _child_bsdf(export_ctx, ref):
    '''Convert a nested shader node into a plain BSDF dict.'''
    result = convert_shader_node(export_ctx, ref)
    if result['emitter'] is not None:
        export_ctx.log(f'Ignoring the emission of node "{ref.node.name}": '
                       'emitters cannot be nested inside a BSDF.', 'WARN')
    if result['bsdf'] is None:
        raise ConversionError(f'node "{ref.node.name}" does not produce a BSDF')
    return result['bsdf']


def _emission_radiance(export_ctx, ref):
    '''Evaluate an Emission node into an RGB radiance list or a Mitsuba
    texture dict (the color scaled by the strength).'''
    node = ref.node
    strength = scalar_from_socket(export_ctx, node.inputs['Strength'], stack=ref.stack)

    color = resolve(export_ctx, node.inputs['Color'], stack=ref.stack)
    if isinstance(color, Texture):
        params = color.params
        if strength != 1.0:
            params = _math('in[0] * in[1]', params, strength)
        return params
    if isinstance(color, Constant):
        rgb = color.value
    else:
        export_ctx.log(f'{color.reason}; using the default value', 'WARN')
        rgb = tuple(node.inputs['Color'].default_value)
    return [c * strength for c in rgb[:3]]


def _emitter_result(export_ctx, radiance):
    '''Wrap a radiance value in an area emitter pair. A zero radiance falls
    back to a black diffuse BSDF since Mitsuba rejects black emitters.'''
    if isinstance(radiance, dict):
        return {'bsdf': None,
                'emitter': {'type': 'area',
                            'radiance': radiance,
                            'twosided': True}
                }
    if sum(radiance) == 0:
        export_ctx.log('Ignoring emitter with zero emission.', 'WARN')
        return {'bsdf': {'type': 'diffuse',
                         'reflectance': export_ctx.spectrum(0.0)},
                'emitter': None}
    return {'bsdf': None,
            'emitter': {'type': 'area',
                        'radiance': export_ctx.spectrum(radiance),
                        'twosided' : True}}


@node_converter('EMISSION')
def convert_emission(export_ctx, ref):
    return _emitter_result(export_ctx, _emission_radiance(export_ctx, ref))


@node_converter('HOLDOUT')
def convert_holdout(export_ctx, ref):
    export_ctx.log(f'Holdout node "{ref.node.name}" is approximated by a '
                   'null BSDF.', 'WARN')
    return {'type': 'null'}


def _shader_input(socket, stack):
    '''Trace a shader input to the node feeding it, as a NodeRef.'''
    child, _, child_stack = trace_source(socket, stack)
    return NodeRef(child, child_stack) if child is not None else None


@node_converter('ADD_SHADER')
def convert_add(export_ctx, ref):
    node = ref.node
    a = _shader_input(node.inputs[0], ref.stack)
    b = _shader_input(node.inputs[1], ref.stack)
    if a is None and b is None:
        raise ConversionError(f'Add Shader node "{node.name}" needs both '
                              'shader inputs linked')
    if a is None:
        return b
    if b is None:
        return a
    a_emits = a.node.type == 'EMISSION'
    b_emits = b.node.type == 'EMISSION'
    if a_emits and b_emits:
        radiance_a = _emission_radiance(export_ctx, a)
        radiance_b = _emission_radiance(export_ctx, b)
        if isinstance(radiance_a, dict) or isinstance(radiance_b, dict):
            raise ConversionError(f'Add Shader node "{node.name}": adding '
                                  'textured emitters is not supported')
        return _emitter_result(export_ctx,
                               [x + y for x, y in zip(radiance_a, radiance_b)])
    if not a_emits and not b_emits:
        raise ConversionError(f'Add Shader node "{node.name}": adding two '
                              'BSDFs is not supported; use a Mix Shader '
                              'instead')

    emission, other = (a, b) if a_emits else (b, a)
    result = convert_shader_node(export_ctx, other)
    if result['bsdf'] is None or result['emitter'] is not None:
        raise ConversionError(f'Add Shader node "{node.name}": only one '
                              'Emission plus one BSDF is supported')
    emitter = _emitter_result(export_ctx,
                              _emission_radiance(export_ctx, emission))
    return {'bsdf': result['bsdf'], 'emitter': emitter['emitter']}


@node_converter('MIX_SHADER')
def convert_mix(export_ctx, ref):
    node = ref.node
    a = _shader_input(node.inputs[1], ref.stack)
    b = _shader_input(node.inputs[2], ref.stack)
    if a is None and b is None:
        raise ConversionError(f'Mix Shader node "{node.name}" needs both '
                              'shader inputs linked')
    if a is None:
        return {
            'type' : 'blendbsdf',
            'weight' : eval_float(export_ctx, node.inputs['Fac'], stack=ref.stack),
            'bsdf1': {'type' : 'null'},
            'bsdf2': _child_bsdf(export_ctx, b)
        }
    if b is None:
        return {
            'type' : 'blendbsdf',
            'weight' : eval_float(export_ctx, node.inputs['Fac'], stack=ref.stack),
            'bsdf1': _child_bsdf(export_ctx, a),
            'bsdf2': {'type' : 'null'}
        }

    a_emits = a.node.type == 'EMISSION'
    b_emits = b.node.type == 'EMISSION'
    if a_emits and b_emits:
        return _mix_emitters(export_ctx, ref, a, b)
    if a_emits or b_emits:
        raise ConversionError(f'Mix Shader node "{node.name}": mixing a '
                              'BSDF with an emitter is not supported; use '
                              'an Add Shader instead')
    if a.node.type == 'BSDF_TRANSPARENT' or b.node.type == 'BSDF_TRANSPARENT':
        return _mix_transparent(export_ctx, ref, a, b)
    return {
        'type': 'blendbsdf',
        'weight': eval_float(export_ctx, node.inputs['Fac'], stack=ref.stack),
        'bsdf1': _child_bsdf(export_ctx, a),
        'bsdf2': _child_bsdf(export_ctx, b),
    }


def _mix_emitters(export_ctx, ref, a, b):
    node = ref.node
    weight = scalar_from_socket(export_ctx, node.inputs['Fac'], stack=ref.stack)

    radiance_a = _emission_radiance(export_ctx, a)
    radiance_b = _emission_radiance(export_ctx, b)
    if isinstance(radiance_a, dict) or isinstance(radiance_b, dict):
        raise ConversionError(f'Mix Shader node "{node.name}": mixing '
                              'textured emitters is not supported')
    return _emitter_result(
        export_ctx, [(1.0 - weight) * x + weight * y
                     for x, y in zip(radiance_a, radiance_b)])


def _warn_transparent_tint(export_ctx, ref):
    node = ref.node
    color = resolve(export_ctx, node.inputs['Color'], stack=ref.stack)
    if not isinstance(color, Constant) or \
            any(c != 1.0 for c in color.value[:3]):
        export_ctx.log(f'Ignoring the tint of Transparent BSDF node '
                       f'"{node.name}" inside a Mix Shader.', 'WARN')


def _mix_transparent(export_ctx, ref, a, b):
    '''A Mix Shader with a Transparent BSDF on one side maps to a Mitsuba
    mask, whose opacity gives the weight of the nested BSDF.'''
    node = ref.node
    if a.node.type == 'BSDF_TRANSPARENT' and b.node.type == 'BSDF_TRANSPARENT':
        _warn_transparent_tint(export_ctx, a)
        _warn_transparent_tint(export_ctx, b)
        return {'type': 'null'}
    if a.node.type == 'BSDF_TRANSPARENT':
        transparent, opaque, invert = a, b, False
    else:
        transparent, opaque, invert = b, a, True
    _warn_transparent_tint(export_ctx, transparent)
    opacity = eval_float(export_ctx, node.inputs['Fac'], stack=ref.stack)
    if invert:
        if isinstance(opacity, dict):
            # 1 - texture cannot be expressed; a blend against a null BSDF
            # is equivalent to a mask with the inverted opacity
            return {
                'type': 'blendbsdf',
                'weight': opacity,
                'bsdf1': _child_bsdf(export_ctx, opaque),
                'bsdf2': {'type': 'null'},
            }
        opacity = 1.0 - opacity
    return {
        'type': 'mask',
        'opacity': opacity,
        'bsdf': _child_bsdf(export_ctx, opaque),
    }
