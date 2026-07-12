'''Blender world to Mitsuba environment emitter conversion.

Supports a Background or Emission surface node with either a constant
color (folded through the material evaluator, so RGB/Math/Mix chains
work) or an Environment Texture, optionally rotated through a Mapping
node driven by generated texture coordinates.
'''

from mathutils import Euler, Matrix, Vector

from .. import ConversionError
from ...compat import uses_nodes
from .materials import _eval
from .materials.textures import convert_environment_texture

# The color of Blender's default gray world background.
DEFAULT_BACKGROUND = [0.05087608844041824] * 3

# Aligns Mitsuba's equirectangular parametrization with Blender's.
ENVMAP_COORDINATE_MAT = Matrix(((0, 0, 1, 0),
                                (1, 0, 0, 0),
                                (0, 1, 0, 0),
                                (0, 0, 0, 1)))


def _constant_vector(export_ctx, socket):
    '''Fold a vector socket to a constant, or fail.'''
    result = _eval.resolve(export_ctx, socket)
    if not isinstance(result, _eval.Constant):
        raise ConversionError(f'input "{socket.name}" of node '
                              f'"{socket.node.name}" does not fold to a '
                              'constant')
    value = result.value
    if isinstance(value, float):
        value = (value,) * 3
    return Vector(value[:3])


def _mapping_transform(export_ctx, vector_socket):
    '''The world transform of an environment texture, from an optional
    Mapping node feeding its Vector input.'''
    node, _ = _eval.trace_source(vector_socket)
    if node is None:
        return Matrix()
    if node.type != 'MAPPING':
        raise ConversionError(f'node "{node.name}" of type {node.type} '
                              'cannot drive an environment texture; only '
                              'a Mapping node is supported')
    coord_node, coord_socket = _eval.trace_source(node.inputs['Vector'])
    if coord_node is None or coord_node.type != 'TEX_COORD' \
            or coord_socket.name != 'Generated':
        raise ConversionError('the Mapping node must be driven by the '
                              '"Generated" output of a Texture Coordinate '
                              'node')
    matrix = Matrix.LocRotScale(
        _constant_vector(export_ctx, node.inputs['Location']),
        Euler(_constant_vector(export_ctx, node.inputs['Rotation'])),
        _constant_vector(export_ctx, node.inputs['Scale']))
    if node.vector_type == 'TEXTURE':
        # Texture mappings look up the texture at the inverse-transformed
        # coordinate, matching Mitsuba's to_world convention directly
        return matrix
    if node.vector_type == 'POINT':
        return matrix.inverted()
    raise ConversionError(f'mapping type {node.vector_type} is not '
                          'supported; use "Point" or "Texture"')


def _convert_envmap(export_ctx, node, strength):
    params = convert_environment_texture(export_ctx, node)
    to_world = _mapping_transform(export_ctx, node.inputs['Vector'])
    params['scale'] = strength
    params['to_world'] = export_ctx.transform_matrix(
        to_world @ ENVMAP_COORDINATE_MAT)
    return params


def _constant_color(result):
    value = result.value
    if isinstance(value, float):
        return [value] * 3
    return list(value[:3])


def convert_world(export_ctx, b_world, ignore_background=True):
    '''Convert a Blender world into a Mitsuba emitter dict. Returns None
    when there is nothing to export; raises ConversionError for
    unsupported node setups.'''
    if b_world is None:
        export_ctx.log('No Blender world to export.', 'INFO')
        return None

    if not uses_nodes(b_world):
        return {
            'type': 'constant',
            'radiance': export_ctx.spectrum(list(b_world.color)),
        }

    output = b_world.node_tree.get_output_node('CYCLES')
    if output is None:
        raise ConversionError('cannot find the world output node')
    node, _ = _eval.trace_source(output.inputs['Surface'])
    if node is None:
        return None
    if node.type not in ('BACKGROUND', 'EMISSION'):
        raise ConversionError(f'node "{node.name}" of type {node.type} is '
                              'not supported as the world surface; only '
                              'Background and Emission nodes are')

    strength = _eval.eval_float(export_ctx, node.inputs['Strength'])
    if not isinstance(strength, (int, float)):
        raise ConversionError('the world strength must be a constant')
    if strength == 0.0:
        export_ctx.log('Ignoring a world with zero strength.', 'INFO')
        return None

    color_socket = node.inputs['Color']
    source, _ = _eval.trace_source(color_socket)
    if source is not None and source.type == 'TEX_ENVIRONMENT':
        return _convert_envmap(export_ctx, source, strength)

    result = _eval.resolve(export_ctx, color_socket)
    if not isinstance(result, _eval.Constant):
        reason = result.reason if isinstance(result, _eval.Unsupported) \
            else 'only environment textures and constant colors are supported'
        raise ConversionError(reason)

    radiance = [c * strength for c in _constant_color(result)]
    if ignore_background and radiance == DEFAULT_BACKGROUND:
        export_ctx.log("Ignoring Blender's default background.", 'INFO')
        return None
    if sum(radiance) == 0.0:
        export_ctx.log('Ignoring a background with zero emission.', 'INFO')
        return None
    return {
        'type': 'constant',
        'radiance': export_ctx.spectrum(radiance),
    }


def export_world(export_ctx, b_world, ignore_background=True):
    '''Convert the world and add it to the scene dict. Never raises:
    failures produce a warning and the world is skipped.'''
    try:
        params = convert_world(export_ctx, b_world, ignore_background)
    except Exception as e:
        export_ctx.log(f'Failed to export the world: {e}. Skipping it.',
                       'WARN')
        return
    if params is None:
        return
    if export_ctx.export_ids:
        export_ctx.data_add(params, 'World')
    else:
        export_ctx.data_add(params)
