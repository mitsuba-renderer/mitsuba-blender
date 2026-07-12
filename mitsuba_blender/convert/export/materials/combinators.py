'''Converters for the shader combinator nodes: Mix Shader, Add Shader,
Emission and Holdout.'''

from ... import ConversionError
from . import convert_shader_node, node_converter
from ._eval import Constant, Texture, resolve, eval_float, trace_source


def _child_bsdf(export_ctx, node):
    '''Convert a nested shader node into a plain BSDF dict.'''
    result = convert_shader_node(export_ctx, node)
    if result['emitter'] is not None:
        export_ctx.log(f'Ignoring the emission of node "{node.name}": '
                       'emitters cannot be nested inside a BSDF.', 'WARN')
    if result['bsdf'] is None:
        raise ConversionError(f'node "{node.name}" does not produce a BSDF')
    return result['bsdf']


def _emission_radiance(export_ctx, node):
    '''Evaluate an Emission node into an RGB radiance list or a Mitsuba
    texture dict (the color scaled by the strength).'''
    strength = resolve(export_ctx, node.inputs['Strength'])
    if isinstance(strength, Constant):
        strength = strength.value
    else:
        reason = getattr(strength, 'reason',
                         'textured emission strength is not supported')
        export_ctx.log(f'{reason}; using the default value', 'WARN')
        strength = node.inputs['Strength'].default_value

    color = resolve(export_ctx, node.inputs['Color'])
    if isinstance(color, Texture):
        if strength != 1.0:
            # Mitsuba has no texture-scaling plugin, so the strength is lost
            export_ctx.log(f'Emission node "{node.name}": cannot scale a '
                           'textured color by the strength; ignoring it.',
                           'WARN')
        return color.params
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
                'emitter': {'type': 'area', 'radiance': radiance}}
    if sum(radiance) == 0:
        export_ctx.log('Ignoring emitter with zero emission.', 'WARN')
        return {'bsdf': {'type': 'diffuse',
                         'reflectance': export_ctx.spectrum(0.0)},
                'emitter': None}
    return {'bsdf': None,
            'emitter': {'type': 'area',
                        'radiance': export_ctx.spectrum(radiance)}}


@node_converter('EMISSION')
def convert_emission(export_ctx, node):
    return _emitter_result(export_ctx, _emission_radiance(export_ctx, node))


@node_converter('HOLDOUT')
def convert_holdout(export_ctx, node):
    export_ctx.log(f'Holdout node "{node.name}" is approximated by a null '
                   'BSDF.', 'WARN')
    return {'type': 'null'}


@node_converter('ADD_SHADER')
def convert_add(export_ctx, node):
    a, _ = trace_source(node.inputs[0])
    b, _ = trace_source(node.inputs[1])
    if a is None or b is None:
        raise ConversionError(f'Add Shader node "{node.name}" needs both '
                              'shader inputs linked')
    a_emits, b_emits = a.type == 'EMISSION', b.type == 'EMISSION'
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
def convert_mix(export_ctx, node):
    a, _ = trace_source(node.inputs[1])
    b, _ = trace_source(node.inputs[2])
    if a is None or b is None:
        raise ConversionError(f'Mix Shader node "{node.name}" needs both '
                              'shader inputs linked')
    a_emits, b_emits = a.type == 'EMISSION', b.type == 'EMISSION'
    if a_emits and b_emits:
        return _mix_emitters(export_ctx, node, a, b)
    if a_emits or b_emits:
        raise ConversionError(f'Mix Shader node "{node.name}": mixing a '
                              'BSDF with an emitter is not supported; use '
                              'an Add Shader instead')
    if a.type == 'BSDF_TRANSPARENT' or b.type == 'BSDF_TRANSPARENT':
        return _mix_transparent(export_ctx, node, a, b)
    return {
        'type': 'blendbsdf',
        'weight': eval_float(export_ctx, node.inputs['Fac']),
        'bsdf1': _child_bsdf(export_ctx, a),
        'bsdf2': _child_bsdf(export_ctx, b),
    }


def _mix_emitters(export_ctx, node, a, b):
    fac = resolve(export_ctx, node.inputs['Fac'])
    if not isinstance(fac, Constant):
        raise ConversionError(f'Mix Shader node "{node.name}": only a '
                              'constant factor is supported when mixing '
                              'emitters')
    radiance_a = _emission_radiance(export_ctx, a)
    radiance_b = _emission_radiance(export_ctx, b)
    if isinstance(radiance_a, dict) or isinstance(radiance_b, dict):
        raise ConversionError(f'Mix Shader node "{node.name}": mixing '
                              'textured emitters is not supported')
    weight = fac.value
    return _emitter_result(
        export_ctx, [(1.0 - weight) * x + weight * y
                     for x, y in zip(radiance_a, radiance_b)])


def _warn_transparent_tint(export_ctx, node):
    color = resolve(export_ctx, node.inputs['Color'])
    if not isinstance(color, Constant) or \
            any(c != 1.0 for c in color.value[:3]):
        export_ctx.log(f'Ignoring the tint of Transparent BSDF node '
                       f'"{node.name}" inside a Mix Shader.', 'WARN')


def _mix_transparent(export_ctx, node, a, b):
    '''A Mix Shader with a Transparent BSDF on one side maps to a Mitsuba
    mask, whose opacity gives the weight of the nested BSDF.'''
    if a.type == 'BSDF_TRANSPARENT' and b.type == 'BSDF_TRANSPARENT':
        _warn_transparent_tint(export_ctx, a)
        _warn_transparent_tint(export_ctx, b)
        return {'type': 'null'}
    if a.type == 'BSDF_TRANSPARENT':
        transparent, opaque, invert = a, b, False
    else:
        transparent, opaque, invert = b, a, True
    _warn_transparent_tint(export_ctx, transparent)
    opacity = eval_float(export_ctx, node.inputs['Fac'])
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
