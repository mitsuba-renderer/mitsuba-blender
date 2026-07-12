'''Socket resolution and constant folding for material export.

`resolve` follows node links through reroutes and muted nodes and classifies
what feeds an input socket:

- `Constant(value)`: the socket is unlinked, or fed by a subgraph built
  entirely from value nodes (Math, Mix, RGB, ...) that is evaluated here,
- `Texture(params)`: the socket is fed by a node with a registered texture
  converter, and `params` is the resulting Mitsuba texture dict,
- `Unsupported(reason)`: anything else, with a message naming the node that
  could not be handled.
'''

import colorsys
import math

from ... import ConversionError


class Constant:
    '''A folded constant: a float, or a tuple for vectors and colors.'''

    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return f'Constant({self.value!r})'


class Texture:
    '''A Mitsuba texture dict produced by a registered texture converter.'''

    def __init__(self, params):
        self.params = params

    def __repr__(self):
        return f'Texture({self.params!r})'


class Unsupported:
    '''Marks a socket whose input cannot be converted, with the reason.'''

    def __init__(self, reason):
        self.reason = reason

    def __repr__(self):
        return f'Unsupported({self.reason!r})'


_texture_converters = {}


def texture_converter(*node_types):
    '''Register a converter for a texture-producing shader node type (the
    value of `node.type`, e.g. TEX_IMAGE). The function receives
    (export_ctx, node, out_socket) and returns a Mitsuba texture dict, or
    raises ConversionError.'''
    def decorator(func):
        for node_type in node_types:
            _texture_converters[node_type] = func
        return func
    return decorator


def trace_source(socket):
    '''Return the (node, output socket) pair feeding an input socket,
    skipping reroutes and muted nodes. Returns (None, None) when nothing is
    effectively connected; raises ConversionError when the links form a
    cycle (Blender permits cycles made of reroutes or muted nodes).'''
    visited = set()
    while socket.is_linked:
        if socket.as_pointer() in visited:
            raise ConversionError(f'the links feeding socket '
                                  f'"{socket.name}" of node '
                                  f'"{socket.node.name}" form a cycle')
        visited.add(socket.as_pointer())
        link = socket.links[0]
        if link.is_muted or not link.is_valid:
            return None, None
        node, source = link.from_node, link.from_socket
        if node.type == 'REROUTE':
            socket = node.inputs[0]
            continue
        if node.mute:
            internal = [l for l in node.internal_links
                        if l.to_socket == source]
            if not internal:
                return None, None
            socket = internal[0].from_socket
            continue
        return node, source
    return None, None


def socket_default(socket):
    '''The default value of a socket, as a float or tuple.'''
    value = socket.default_value
    if isinstance(value, (int, float)):
        return float(value)
    return tuple(value)


def resolve(export_ctx, socket):
    '''Classify the input of a socket as Constant, Texture or Unsupported.'''
    try:
        node, source = trace_source(socket)
    except ConversionError as e:
        return Unsupported(str(e))
    if node is None:
        return Constant(socket_default(socket))
    converter = _texture_converters.get(node.type)
    if converter is not None:
        try:
            return Texture(converter(export_ctx, node, source))
        except ConversionError as e:
            return Unsupported(str(e))
    try:
        return Constant(_convert(_fold_node(node, source), socket.type))
    except _Unfoldable as e:
        return Unsupported(f'{e} (feeding socket "{socket.name}" of node '
                           f'"{socket.node.name}")')


def eval_float(export_ctx, socket, default=None):
    '''Resolve a float socket to a float or a Mitsuba texture dict. On
    unsupported input, a warning is logged and the default is used (the
    socket default if none is given).'''
    result = resolve(export_ctx, socket)
    if isinstance(result, Constant):
        return _to_float(result.value)
    if isinstance(result, Texture):
        return result.params
    export_ctx.log(f'{result.reason}; using the default value', 'WARN')
    return _to_float(default if default is not None else socket_default(socket))


def eval_color(export_ctx, socket, default=None):
    '''Resolve a color socket to a Mitsuba spectrum or texture dict. On
    unsupported input, a warning is logged and the default is used (the
    socket default if none is given).'''
    result = resolve(export_ctx, socket)
    if isinstance(result, Constant):
        return export_ctx.spectrum(list(_to_color(result.value)))
    if isinstance(result, Texture):
        return result.params
    export_ctx.log(f'{result.reason}; using the default value', 'WARN')
    if default is None:
        default = socket_default(socket)
    return export_ctx.spectrum(list(_to_color(default)))


#############################
##  Value representations  ##
#############################

# Folded values are floats, 3-tuples (vectors) or 4-tuples (RGBA colors).
# The conversions between them mirror Blender's implicit socket conversions.

class _Unfoldable(Exception):
    pass


def _luminance(rgb):
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def _to_float(value):
    if isinstance(value, (int, float)):
        return float(value)
    if len(value) == 4:
        return _luminance(value)
    return sum(value) / 3.0


def _to_vector(value):
    if isinstance(value, (int, float)):
        return (float(value),) * 3
    return tuple(value)[:3]


def _to_color(value):
    if isinstance(value, (int, float)):
        value = float(value)
        return (value, value, value, 1.0)
    value = tuple(value)
    if len(value) == 3:
        return value + (1.0,)
    return value


_SOCKET_CONVERTERS = {
    'VALUE': _to_float,
    'VECTOR': _to_vector,
    'RGBA': _to_color,
}


def _convert(value, socket_type):
    converter = _SOCKET_CONVERTERS.get(socket_type)
    if converter is None:
        raise _Unfoldable(f'cannot fold into a socket of type {socket_type}')
    return converter(value)


####################
##  Folding core  ##
####################

def _fold_node(node, out_socket):
    if node.type in _texture_converters:
        raise _Unfoldable(f'node "{node.name}" of type {node.type} produces '
                          'a texture inside a constant subgraph')
    folder = _FOLDERS.get(node.type)
    if folder is None:
        raise _Unfoldable(f'node "{node.name}" of type {node.type} is not '
                          'supported')
    return folder(node, out_socket)


# Sockets whose _fold_input is currently on the call stack, to detect
# link cycles that pass through foldable nodes
_folding = set()


def _fold_input(socket):
    try:
        node, source = trace_source(socket)
    except ConversionError as e:
        raise _Unfoldable(str(e)) from None
    if node is None:
        return socket_default(socket)
    key = socket.as_pointer()
    if key in _folding:
        raise _Unfoldable(f'the links feeding socket "{socket.name}" of '
                          f'node "{socket.node.name}" form a cycle')
    _folding.add(key)
    try:
        return _convert(_fold_node(node, source), socket.type)
    finally:
        _folding.discard(key)


def _input(node, key):
    if isinstance(key, int):
        return node.inputs[key]
    for socket in node.inputs:
        if socket.identifier == key:
            return socket
    raise _Unfoldable(f'node "{node.name}" has no input socket "{key}"')


def _float_in(node, key):
    return _to_float(_fold_input(_input(node, key)))


def _vector_in(node, key):
    return _to_vector(_fold_input(_input(node, key)))


def _color_in(node, key):
    return _to_color(_fold_input(_input(node, key)))


##################
##  Arithmetic  ##
##################

def _clamp(value, lo=0.0, hi=1.0):
    return min(max(value, lo), hi)


def _mix(a, b, t):
    return a + (b - a) * t


def _safe_divide(a, b):
    return a / b if b != 0.0 else 0.0


def _safe_power(a, b):
    try:
        return math.pow(a, b)
    except (ValueError, OverflowError):
        return 0.0


def _safe_log(a, b):
    if a <= 0.0 or b <= 0.0 or b == 1.0:
        return 0.0
    return math.log(a, b)


def _fract(a):
    return a - math.floor(a)


def _wrap(a, b, c):
    rng = b - c
    return a - rng * math.floor((a - c) / rng) if rng != 0.0 else c


def _pingpong(a, b):
    if b == 0.0:
        return 0.0
    return abs(_fract((a - b) / (b * 2.0)) * b * 2.0 - b)


def _smooth_min(a, b, k):
    if k != 0.0:
        h = max(k - abs(a - b), 0.0) / k
        return min(a, b) - h * h * h * k * (1.0 / 6.0)
    return min(a, b)


_MATH_OPS = {
    'ADD': lambda a, b, c: a + b,
    'SUBTRACT': lambda a, b, c: a - b,
    'MULTIPLY': lambda a, b, c: a * b,
    'DIVIDE': lambda a, b, c: _safe_divide(a, b),
    'MULTIPLY_ADD': lambda a, b, c: a * b + c,
    'POWER': lambda a, b, c: _safe_power(a, b),
    'LOGARITHM': lambda a, b, c: _safe_log(a, b),
    'SQRT': lambda a, b, c: math.sqrt(a) if a >= 0.0 else 0.0,
    'INVERSE_SQRT': lambda a, b, c: 1.0 / math.sqrt(a) if a > 0.0 else 0.0,
    'ABSOLUTE': lambda a, b, c: abs(a),
    'EXPONENT': lambda a, b, c: math.exp(a),
    'MINIMUM': lambda a, b, c: min(a, b),
    'MAXIMUM': lambda a, b, c: max(a, b),
    'LESS_THAN': lambda a, b, c: 1.0 if a < b else 0.0,
    'GREATER_THAN': lambda a, b, c: 1.0 if a > b else 0.0,
    'SIGN': lambda a, b, c: float((a > 0.0) - (a < 0.0)),
    'COMPARE': lambda a, b, c: 1.0 if abs(a - b) <= max(c, 1e-5) else 0.0,
    'SMOOTH_MIN': lambda a, b, c: _smooth_min(a, b, c),
    'SMOOTH_MAX': lambda a, b, c: -_smooth_min(-a, -b, c),
    'ROUND': lambda a, b, c: math.floor(a + 0.5),
    'FLOOR': lambda a, b, c: math.floor(a),
    'CEIL': lambda a, b, c: math.ceil(a),
    'TRUNC': lambda a, b, c: float(math.trunc(a)),
    'FRACT': lambda a, b, c: _fract(a),
    'MODULO': lambda a, b, c: math.fmod(a, b) if b != 0.0 else 0.0,
    'FLOORED_MODULO': lambda a, b, c:
        a - math.floor(a / b) * b if b != 0.0 else 0.0,
    'WRAP': lambda a, b, c: _wrap(a, b, c),
    'SNAP': lambda a, b, c: math.floor(_safe_divide(a, b)) * b,
    'PINGPONG': lambda a, b, c: _pingpong(a, b),
    'SINE': lambda a, b, c: math.sin(a),
    'COSINE': lambda a, b, c: math.cos(a),
    'TANGENT': lambda a, b, c: math.tan(a),
    'ARCSINE': lambda a, b, c: math.asin(_clamp(a, -1.0, 1.0)),
    'ARCCOSINE': lambda a, b, c: math.acos(_clamp(a, -1.0, 1.0)),
    'ARCTANGENT': lambda a, b, c: math.atan(a),
    'ARCTAN2': lambda a, b, c: math.atan2(a, b),
    'SINH': lambda a, b, c: math.sinh(a),
    'COSH': lambda a, b, c: math.cosh(a),
    'TANH': lambda a, b, c: math.tanh(a),
    'RADIANS': lambda a, b, c: math.radians(a),
    'DEGREES': lambda a, b, c: math.degrees(a),
}


def _fold_math(node, out_socket):
    op = _MATH_OPS.get(node.operation)
    if op is None:
        raise _Unfoldable(f'node "{node.name}": Math operation '
                          f'{node.operation} is not supported')
    value = op(_float_in(node, 0), _float_in(node, 1), _float_in(node, 2))
    return _clamp(value) if node.use_clamp else value


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _length(a):
    return math.sqrt(_dot(a, a))


def _normalize(a):
    norm = _length(a)
    return tuple(x / norm for x in a) if norm > 0.0 else (0.0, 0.0, 0.0)


_VECTOR_OPS = {
    'ADD': lambda a, b, c, s: tuple(x + y for x, y in zip(a, b)),
    'SUBTRACT': lambda a, b, c, s: tuple(x - y for x, y in zip(a, b)),
    'MULTIPLY': lambda a, b, c, s: tuple(x * y for x, y in zip(a, b)),
    'DIVIDE': lambda a, b, c, s:
        tuple(_safe_divide(x, y) for x, y in zip(a, b)),
    'MULTIPLY_ADD': lambda a, b, c, s:
        tuple(x * y + z for x, y, z in zip(a, b, c)),
    'CROSS_PRODUCT': lambda a, b, c, s: (a[1] * b[2] - a[2] * b[1],
                                         a[2] * b[0] - a[0] * b[2],
                                         a[0] * b[1] - a[1] * b[0]),
    'DOT_PRODUCT': lambda a, b, c, s: _dot(a, b),
    'DISTANCE': lambda a, b, c, s:
        _length(tuple(x - y for x, y in zip(a, b))),
    'LENGTH': lambda a, b, c, s: _length(a),
    'SCALE': lambda a, b, c, s: tuple(x * s for x in a),
    'NORMALIZE': lambda a, b, c, s: _normalize(a),
    'ABSOLUTE': lambda a, b, c, s: tuple(abs(x) for x in a),
    'MINIMUM': lambda a, b, c, s: tuple(min(x, y) for x, y in zip(a, b)),
    'MAXIMUM': lambda a, b, c, s: tuple(max(x, y) for x, y in zip(a, b)),
    'FLOOR': lambda a, b, c, s: tuple(math.floor(x) for x in a),
    'CEIL': lambda a, b, c, s: tuple(math.ceil(x) for x in a),
    'FRACTION': lambda a, b, c, s: tuple(_fract(x) for x in a),
    'MODULO': lambda a, b, c, s:
        tuple(math.fmod(x, y) if y != 0.0 else 0.0 for x, y in zip(a, b)),
    'SINE': lambda a, b, c, s: tuple(math.sin(x) for x in a),
    'COSINE': lambda a, b, c, s: tuple(math.cos(x) for x in a),
    'TANGENT': lambda a, b, c, s: tuple(math.tan(x) for x in a),
}


def _fold_vector_math(node, out_socket):
    op = _VECTOR_OPS.get(node.operation)
    if op is None:
        raise _Unfoldable(f'node "{node.name}": Vector Math operation '
                          f'{node.operation} is not supported')
    return op(_vector_in(node, 'Vector'), _vector_in(node, 'Vector_001'),
              _vector_in(node, 'Vector_002'), _float_in(node, 'Scale'))


def _blend_color(blend_type, a, b, t):
    '''Blend two RGB tuples with factor t, following Blender's ramp_blend.'''
    facm = 1.0 - t
    if blend_type == 'MIX':
        return tuple(_mix(x, y, t) for x, y in zip(a, b))
    if blend_type == 'ADD':
        return tuple(x + t * y for x, y in zip(a, b))
    if blend_type == 'MULTIPLY':
        return tuple(x * (facm + t * y) for x, y in zip(a, b))
    if blend_type == 'SUBTRACT':
        return tuple(x - t * y for x, y in zip(a, b))
    if blend_type == 'SCREEN':
        return tuple(1.0 - (facm + t * (1.0 - y)) * (1.0 - x)
                     for x, y in zip(a, b))
    if blend_type == 'DIVIDE':
        return tuple(facm * x + t * x / y if y != 0.0 else x
                     for x, y in zip(a, b))
    if blend_type == 'DIFFERENCE':
        return tuple(facm * x + t * abs(x - y) for x, y in zip(a, b))
    if blend_type == 'DARKEN':
        return tuple(_mix(x, min(x, y), t) for x, y in zip(a, b))
    if blend_type == 'LIGHTEN':
        return tuple(max(x, t * y) for x, y in zip(a, b))
    return None


def _fold_mix(node, out_socket):
    data_type = node.data_type
    if data_type == 'FLOAT':
        t = _float_in(node, 'Factor_Float')
        if node.clamp_factor:
            t = _clamp(t)
        return _mix(_float_in(node, 'A_Float'), _float_in(node, 'B_Float'), t)
    if data_type == 'VECTOR':
        if node.factor_mode == 'NON_UNIFORM':
            t = _vector_in(node, 'Factor_Vector')
        else:
            t = (_float_in(node, 'Factor_Float'),) * 3
        if node.clamp_factor:
            t = tuple(_clamp(x) for x in t)
        return tuple(_mix(x, y, f) for x, y, f in
                     zip(_vector_in(node, 'A_Vector'),
                         _vector_in(node, 'B_Vector'), t))
    if data_type == 'RGBA':
        t = _float_in(node, 'Factor_Float')
        if node.clamp_factor:
            t = _clamp(t)
        a = _color_in(node, 'A_Color')
        b = _color_in(node, 'B_Color')
        rgb = _blend_color(node.blend_type, a[:3], b[:3], t)
        if rgb is None:
            raise _Unfoldable(f'node "{node.name}": Mix blend type '
                              f'{node.blend_type} is not supported')
        if node.clamp_result:
            rgb = tuple(_clamp(x) for x in rgb)
        return rgb + (a[3],)
    raise _Unfoldable(f'node "{node.name}": Mix data type {data_type} is '
                      'not supported')


####################
##  Simple nodes  ##
####################

def _fold_rgb(node, out_socket):
    # The value lives on the output socket; node.color is the header color.
    return tuple(node.outputs['Color'].default_value)


def _fold_value(node, out_socket):
    return float(node.outputs['Value'].default_value)


def _fold_invert(node, out_socket):
    fac = _float_in(node, 'Fac')
    color = _color_in(node, 'Color')
    return tuple(_mix(x, 1.0 - x, fac) for x in color[:3]) + (color[3],)


def _fold_gamma(node, out_socket):
    color = _color_in(node, 'Color')
    gamma = _float_in(node, 'Gamma')
    return tuple(math.pow(x, gamma) if x > 0.0 else x
                 for x in color[:3]) + (color[3],)


def _fold_bright_contrast(node, out_socket):
    color = _color_in(node, 'Color')
    contrast = _float_in(node, 'Contrast')
    gain = 1.0 + contrast
    offset = _float_in(node, 'Bright') - contrast * 0.5
    return tuple(max(gain * x + offset, 0.0)
                 for x in color[:3]) + (color[3],)


def _fold_map_range(node, out_socket):
    if node.data_type != 'FLOAT':
        raise _Unfoldable(f'node "{node.name}": Map Range data type '
                          f'{node.data_type} is not supported')
    to_min = _float_in(node, 'To Min')
    to_max = _float_in(node, 'To Max')
    from_min = _float_in(node, 'From Min')
    fac = _safe_divide(_float_in(node, 'Value') - from_min,
                       _float_in(node, 'From Max') - from_min)
    interpolation = node.interpolation_type
    if interpolation == 'STEPPED':
        steps = _float_in(node, 'Steps')
        fac = math.floor(fac * (steps + 1.0)) / steps if steps > 0.0 else 0.0
    elif interpolation == 'SMOOTHSTEP':
        fac = _clamp(fac)
        fac = fac * fac * (3.0 - 2.0 * fac)
    elif interpolation == 'SMOOTHERSTEP':
        fac = _clamp(fac)
        fac = fac ** 3 * (fac * (fac * 6.0 - 15.0) + 10.0)
    result = _mix(to_min, to_max, fac)
    if node.clamp and interpolation in ('LINEAR', 'STEPPED'):
        result = _clamp(result, min(to_min, to_max), max(to_min, to_max))
    return result


def _fold_clamp(node, out_socket):
    lo = _float_in(node, 'Min')
    hi = _float_in(node, 'Max')
    if node.clamp_type == 'RANGE' and lo > hi:
        lo, hi = hi, lo
    return _clamp(_float_in(node, 'Value'), lo, hi)


def _fold_separate_xyz(node, out_socket):
    return _vector_in(node, 'Vector')['XYZ'.index(out_socket.name)]


def _fold_combine_xyz(node, out_socket):
    return (_float_in(node, 'X'), _float_in(node, 'Y'), _float_in(node, 'Z'))


def _fold_separate_color(node, out_socket):
    rgb = _color_in(node, 'Color')[:3]
    if node.mode == 'RGB':
        components = rgb
    elif node.mode == 'HSV':
        components = colorsys.rgb_to_hsv(*rgb)
    elif node.mode == 'HSL':
        h, l, s = colorsys.rgb_to_hls(*rgb)
        components = (h, s, l)
    else:
        raise _Unfoldable(f'node "{node.name}": color mode {node.mode} is '
                          'not supported')
    return components[('Red', 'Green', 'Blue').index(out_socket.name)]


def _fold_combine_color(node, out_socket):
    x = _float_in(node, 'Red')
    y = _float_in(node, 'Green')
    z = _float_in(node, 'Blue')
    if node.mode == 'RGB':
        rgb = (x, y, z)
    elif node.mode == 'HSV':
        rgb = colorsys.hsv_to_rgb(x, y, z)
    elif node.mode == 'HSL':
        rgb = colorsys.hls_to_rgb(x, z, y)
    else:
        raise _Unfoldable(f'node "{node.name}": color mode {node.mode} is '
                          'not supported')
    return rgb + (1.0,)


def _fold_rgb_to_bw(node, out_socket):
    return _luminance(_color_in(node, 'Color'))


_FOLDERS = {
    'MATH': _fold_math,
    'VECT_MATH': _fold_vector_math,
    'MIX': _fold_mix,
    'RGB': _fold_rgb,
    'VALUE': _fold_value,
    'INVERT': _fold_invert,
    'GAMMA': _fold_gamma,
    'BRIGHTCONTRAST': _fold_bright_contrast,
    'MAP_RANGE': _fold_map_range,
    'CLAMP': _fold_clamp,
    'SEPXYZ': _fold_separate_xyz,
    'COMBXYZ': _fold_combine_xyz,
    'SEPARATE_COLOR': _fold_separate_color,
    'COMBINE_COLOR': _fold_combine_color,
    'RGBTOBW': _fold_rgb_to_bw,
}
