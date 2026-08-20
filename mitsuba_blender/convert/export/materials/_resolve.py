'''Socket resolution for material export.

`resolve` follows node links through reroutes and muted nodes and classifies
what feeds an input socket:

- `Constant(value)`: the socket is unlinked
- `Texture(params)`: the socket is fed by a node with a registered texture
  converter, and `params` is the resulting Mitsuba texture dict,
- `Unsupported(reason)`: anything else, with a message naming the node that
  could not be handled.
'''
import mitsuba as mi

from typing import NamedTuple
from ....io.exporter.export_context import ExportContext
from ... import ConversionError

ERROR_COLOR = [1.0, 0.0, 0.3]
FALLBACK_COLOR = [0.5, 0.5, 0.5]

class Constant:
    '''A constant: a float, or a tuple for vectors and colors.'''

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


def _average(texture):
    import drjit as dr
    n = 5
    if 'scalar' in mi.variant():
        total = 0.0
        for i in range(n):
            for j in range(n):
                si = dr.zeros(mi.SurfaceInteraction3f)
                si.uv = mi.Point2f(i / (n - 1), j / (n - 1))
                total += float(texture.eval_1(si))
        return total / (n * n)
    x = dr.linspace(mi.Float, 0.0, 1.0, n)
    x, y = dr.meshgrid(x, x)
    si = dr.zeros(mi.SurfaceInteraction3f, dr.width(x))
    si.uv = mi.Point2f(x, y)
    colors = texture.eval(si)

    avg_color = dr.slice(dr.mean(colors, axis=None), 0)
    return avg_color


def _average_vector(texture):
    import drjit as dr
    n = 5
    if 'scalar' in mi.variant():
        total = [0.0, 0.0, 0.0 ]
        for i in range(n):
            for j in range(n):
                si = dr.zeros(mi.SurfaceInteraction3f)
                si.uv = mi.Point2f(i / (n - 1), j / (n - 1))
                c = texture.eval_3(si)
                total[0] += float(c.x)
                total[1] += float(c.y)
                total[2] += float(c.z)
        return [v / (n * n) for v in total]
    x = dr.linspace(mi.Float, 0.0, 1.0, n)
    x, y = dr.meshgrid(x, x)
    si = dr.zeros(mi.SurfaceInteraction3f, dr.width(x))
    si.uv = mi.Point2f(x, y)

    colors = texture.eval_3(si)
    avg_vector = dr.slice(dr.mean(colors, axis=1), 0)
    return avg_vector


def scalar_from_socket(export_ctx: ExportContext, socket, stack=()) -> float:
    '''
    Average a subgraph down to a scalar for parameters Mitsuba reads as floats.
    '''
    import numpy as np
    result = resolve(export_ctx, socket, stack=stack)
    if isinstance(result, Constant):
        v = result.value
        return float(v) if np.isscalar(v) else float(np.mean(v))
    if isinstance(result, Unsupported):
        return socket_default(socket) 
    # Texture: build it once and average over a UV grid
    texture = mi.load_dict(result.params)
    return _average(texture)


def vector_from_socket(export_ctx: ExportContext, ref, socket):
    result = resolve(export_ctx, socket, stack=ref.stack)
    if isinstance(result, Constant):
        return _to_vector(result.value)
    if isinstance(result, Unsupported):
        if export_ctx.strict:
            raise ConversionError(result.reason)
        return socket_default(socket)
    texture = mi.load_dict(result.params)
    return _average_vector(texture)


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


def _active_output(tree):
    '''The live NodeGroupOutput node of a node group tree, or None

    A tree may hold several Group output nodes, onlty the one flagged
    is_active_output is evaluated, the rest are inert. If nothing is flagged,
    it take the first one'''

    outs = [n for n in tree.nodes if n.type == 'GROUP_OUTPUT']
    return next((n for n in outs if n.is_active_output), None) or (outs[0] if outs else None)

def _index_of(sockets, socket):
    '''The position of `socket` in a node's inputs or outputs collection
    or None if it is not there'''
    for i, s in enumerate(sockets):
        if s == socket:
            return i
    return None


def trace_source(socket, stack=()):
    '''Given an input socket and the current path, return where its values comes from
    This gives us two cases:
        - (node, out_socket, stack) a real node produces the value
        - (node, terminal, stack)   nothing does: `terminal` is where the walk stopped

    Raise a ConversionError when the link form a cycle (Blender permits cycles made
    of retoutes or muted nodes).'''

    visited = set()
    # The loop rewrites `socket` and `stack` in place and iterates.
    # Every branch either moves or stop (return)
    #
    # At the top of each iteration
    # - `socket` is an input socket which we want its feeding value
    # - `stack` lists the group instances we are currently inside, outermost first
    while socket.is_linked:
        key = (socket.as_pointer(), stack)
        if key in visited:
            raise ConversionError(f'the links feeding socket '
                                  f'"{socket.name}" of node '
                                  f'"{socket.node.name}" form a cycle')

        visited.add(key)

        link = socket.links[0]
        if link.is_muted or not link.is_valid:
            return None, socket, stack

        node, source = link.from_node, link.from_socket
        # pass through
        if node.type == 'REROUTE':
            socket = node.inputs[0]

        elif node.mute:
            internal = [l for l in node.internal_links if l.to_socket == source]
            if not internal:
                return None, socket, stack
            socket = internal[0].from_socket

        # We enter into a new group.
        elif node.type == 'GROUP':
            tree = node.node_tree
            if tree is None:
                return None, socket, stack

            active = _active_output(tree)
            if active is None:
                return None, socket, stack

            stack = stack + (node,)
            i = _index_of(node.outputs, source)
            if i is None or i >= len(active.inputs):
                return None, socket, stack

            socket = active.inputs[i]

        # We are going outside the current group, hence we pop it, map the 
        # Group input node's output to the same position input on the group node
        elif node.type == 'GROUP_INPUT':
            if not stack:
                return None, socket, stack
            # Equivalent to stack = list(stack); outer = stack.pop()
            outer, stack = stack[-1], stack[:-1]

            i = _index_of(node.outputs, source)
            if i is None or i >= len(outer.inputs):
                return None, socket, stack

            # outer group input socket for the node.outputs -> source link
            socket = outer.inputs[i]
        else:
            return node, source, stack
    return None, socket, stack

def socket_default(socket):
    '''The default value of a socket, as a float or tuple.'''
    value = socket.default_value
    if isinstance(value, (int, float)):
        return float(value)
    return tuple(value)


def resolve(export_ctx, socket, stack=()):
    '''Classify the input of a socket as Constant, Texture or Unsupported.'''
    try:
        node, source, stack = trace_source(socket, stack=stack)
    except ConversionError as e:
        return Unsupported(str(e))
    if node is None:
        return Constant(socket_default(source))
    ref = NodeRef(node, stack)
    converter = _texture_converters.get(node.type)
    if converter is not None:
        try:
            return Texture(converter(export_ctx, ref, source))
        except ConversionError as e:
            return Unsupported(str(e))
    if ref.node.type in _GETTERS:
        getter = _GETTERS[ref.node.type]
    else:
        return Unsupported(f'node "{node.name}" of type {node.type} is not '
                       f'supported (feeding socket "{socket.name}" of node '
                       f'"{socket.node.name}")')
    try:
            return Constant(_convert(getter(ref, source), socket.type))

    except _Uncastable as e:
        return Unsupported(f'{e} (feeding socket "{socket.name}" of node '
                           f'"{socket.node.name}")')


def eval_float(export_ctx, socket, default=None, stack=()):
    '''Resolve a float socket to a float or a Mitsuba texture dict. On
    unsupported input, a warning is logged and the default is used (the
    socket default if none is given).'''
    result = resolve(export_ctx, socket, stack=stack)
    if isinstance(result, Constant):
        return _to_float(result.value)
    if isinstance(result, Texture):
        return result.params

    if export_ctx.strict:
        raise ConversionError(result.reason)
    export_ctx.log(f'{result.reason}; using the default value', 'WARN')
    return _to_float(default if default is not None else socket_default(socket))


def eval_color(export_ctx, socket, default=None, stack=()):
    '''Resolve a color socket to a Mitsuba spectrum or texture dict. On
    unsupported input, a warning is logged and the default is used (the
    socket default if none is given).'''
    result = resolve(export_ctx, socket, stack=stack)
    if isinstance(result, Constant):
        return export_ctx.spectrum(list(_to_color(result.value)))
    if isinstance(result, Texture):
        return result.params

    if export_ctx.strict:
        raise ConversionError(result.reason)

    export_ctx.log(f'{result.reason}; using the default color', 'WARN')

    return _to_color(default if default is not None else socket_default(socket)) 


def eval_vector(export_ctx, socket, default=None, stack=()):
    '''Resolve a vector socket to a 3-component value or a Mitsuba texture
    dict. Unlike eval_color the result carries no colour semantics, so
    constants are emitted as raw values and the fallback is the socket
    default rather than the error colour.'''

    result = resolve(export_ctx, socket, stack=stack)
    if isinstance(result, Constant):
        return _to_vector(result.value)
    if isinstance(result, Texture):
        return result.params

    if export_ctx.strict:
        raise ConversionError(result.reason)

    export_ctx.log(f'{result.reason}; using the default value', 'WARN')
    return _to_vector(default if default is not None else socket_default(socket))



#############################
##  Value representations  ##
#############################

class _Uncastable(Exception):
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
        raise _Uncastable(f'cannot cast into a socket of type {socket_type}')
    return converter(value)

####################
##  Nodes         ##
####################

class NodeRef(NamedTuple):
    node : object
    stack: tuple


def _get_rgb(ref, out_socket):
    # The value lives on the output socket; node.color is the header color.
    node = ref.node
    return tuple(node.outputs['Color'].default_value)


def _get_value(ref, out_socket):
    node = ref.node
    return float(node.outputs['Value'].default_value)

def _get_object_info(ref, out_socket):
    # TODO: every output here depends on which object (and which instance
    # of it) is being shaded. A Mitsuba texture is evaluated from a
    # SurfaceInteraction, which carries no per-instance identity, so none
    # of these can be reproduced yet. Returning zero until instance data
    # is available: https://github.com/mitsuba-renderer/mitsuba3/pull/1885
    if out_socket.type == 'VALUE':
        return 0.0
    return (0.0, 0.0, 0.0)

_GETTERS = {
    'RGB': _get_rgb,
    'VALUE': _get_value,
    'OBJECT_INFO' : _get_object_info
}
