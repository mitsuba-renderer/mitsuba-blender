'''Converters for Mitsuba texture plugins and for the normalmap/bumpmap
BSDF wrappers, which become Normal Map and Bump nodes feeding the Normal
input of the wrapped BSDF.'''

import os

import bpy
import numpy as np
from mathutils import Matrix

from ... import ConversionError
from . import material_converter, texture_converter

# The inverse of the v -> 1 - v flip the mesh porters apply to UVs
_FLIP = Matrix.Translation((0.0, 1.0, 0.0)) \
    @ Matrix.Diagonal((1.0, -1.0, 1.0, 1.0))


def _references(builder, mi_props, target_type):
    '''Indices of the referenced scene nodes of the given ObjectType.'''
    from mitsuba import Properties
    refs = []
    for _, value in mi_props.items():
        if isinstance(value, Properties.ResolvedReference):
            node = builder.mi_context.mi_state.nodes[value.index()]
            if node.type == target_type:
                refs.append(value.index())
    return refs


def _socket(sockets, identifier):
    return next(s for s in sockets if s.identifier == identifier)


def _multiply(builder, source, value):
    '''Multiply a color socket by a constant via a Mix node.'''
    node = builder.node('ShaderNodeMix')
    node.data_type = 'RGBA'
    node.blend_type = 'MULTIPLY'
    _socket(node.inputs, 'Factor_Float').default_value = 1.0
    builder.link(source, _socket(node.inputs, 'A_Color'))
    if isinstance(value, (int, float)):
        value = (value, value, value)
    _socket(node.inputs, 'B_Color').default_value = (*value[:3], 1.0)
    return _socket(node.outputs, 'Result_Color')


######################
##  UV coordinates  ##
######################

def _uv_matrix(mi_props):
    '''The to_uv transform expressed in Blender UV space, or None.'''
    if 'to_uv' not in mi_props:
        return None
    to_uv = Matrix(np.array(mi_props['to_uv'].matrix).tolist())
    matrix = _FLIP @ to_uv @ _FLIP
    if all(abs(matrix[i][j] - (i == j)) < 1e-8
           for i in range(4) for j in range(4)):
        return None
    return matrix


def _decompose(matrix):
    '''Split a UV-plane transform into (location, z rotation, scale), or
    return None when it contains shear or out-of-plane components.'''
    location, rotation, scale = matrix.decompose()
    euler = rotation.to_euler()
    if abs(euler.x) > 1e-5 or abs(euler.y) > 1e-5:
        return None
    rebuilt = Matrix.Translation(location) @ euler.to_matrix().to_4x4() \
        @ Matrix.Diagonal((*scale, 1.0))
    if any(abs(rebuilt[i][j] - matrix[i][j]) > 1e-4
           for i in range(4) for j in range(4)):
        return None
    return location, euler.z, scale


def _link_mapping(builder, vector_socket, matrix):
    '''Feed a texture Vector input with UV coordinates transformed by the
    given Blender-space matrix.'''
    parts = _decompose(matrix)
    if parts is None:
        builder.mi_context.log(
            'The to_uv transform of a texture cannot be represented by a '
            'Mapping node; ignoring it.', 'WARN')
        return
    location, rotation_z, scale = parts
    mapping = builder.node('ShaderNodeMapping')
    mapping.vector_type = 'POINT'
    mapping.inputs['Location'].default_value = location
    mapping.inputs['Rotation'].default_value = (0.0, 0.0, rotation_z)
    mapping.inputs['Scale'].default_value = scale
    coords = builder.node('ShaderNodeTexCoord')
    builder.link(coords.outputs['UV'], mapping.inputs['Vector'])
    builder.link(mapping.outputs['Vector'], vector_socket)


##########################
##  Texture converters  ##
##########################

def _load_image(mi_context, path, raw):
    key = (os.path.normpath(path), raw)
    if key in mi_context.bl_texture_cache:
        return mi_context.bl_texture_cache[key]
    try:
        image = bpy.data.images.load(path)
    except RuntimeError:
        mi_context.log(f'Failed to load image "{path}".', 'WARN')
        return None
    if raw:
        image.colorspace_settings.is_data = True
        image.colorspace_settings.name = 'Non-Color'
    mi_context.bl_texture_cache[key] = image
    return image


@texture_converter('bitmap')
def convert_bitmap(builder, mi_props):
    ctx = builder.mi_context
    if 'filename' not in mi_props:
        ctx.log('Bitmap textures without a filename are not supported.',
                'WARN')
        return None
    filename = mi_props['filename']
    path = os.path.join(ctx.directory, filename)
    if not os.path.exists(path):
        ctx.log(f'Cannot find the texture file "{filename}".', 'WARN')
        return None
    image = _load_image(ctx, path, bool(mi_props.get('raw', False)))
    if image is None:
        return None

    node = builder.node('ShaderNodeTexImage')
    node.image = image
    wrap_mode = mi_props.get('wrap_mode', 'repeat')
    if wrap_mode == 'clamp':
        node.extension = 'EXTEND'
    elif wrap_mode == 'mirror':
        node.extension = 'MIRROR'
    if mi_props.get('filter_type', 'bilinear') == 'nearest':
        node.interpolation = 'Closest'
    matrix = _uv_matrix(mi_props)
    if matrix is not None:
        _link_mapping(builder, node.inputs['Vector'], matrix)
    return node.outputs['Color']


@texture_converter('checkerboard')
def convert_checkerboard(builder, mi_props):
    node = builder.node('ShaderNodeTexChecker')
    # The UV flip folded into to_uv puts Mitsuba's color1 cells where
    # Blender shows Color1
    builder.set_color(node.inputs['Color1'], mi_props, 'color1',
                      default=(0.2, 0.2, 0.2))
    builder.set_color(node.inputs['Color2'], mi_props, 'color0',
                      default=(0.4, 0.4, 0.4))

    # A Mitsuba checkerboard has 2x2 cells per to_uv period, a Blender one
    # has scale x scale cells per UV unit
    matrix = _uv_matrix(mi_props) or Matrix.Identity(4)
    cells = Matrix.Diagonal((2.0, 2.0, 1.0, 1.0)) @ matrix
    for i in range(2):
        # Translations by an even number of cells do not alter the pattern
        offset = 2.0 * round(cells[i][3] / 2.0)
        if abs(cells[i][3] - offset) < 1e-5:
            cells[i][3] -= offset

    parts = _decompose(cells)
    if parts is not None:
        location, rotation_z, scale = parts
        if location.length < 1e-6 and abs(rotation_z) < 1e-6 \
                and abs(scale.x - scale.y) < 1e-6:
            node.inputs['Scale'].default_value = scale.x
            return node.outputs['Color']
    node.inputs['Scale'].default_value = 1.0
    _link_mapping(builder, node.inputs['Vector'], cells)
    return node.outputs['Color']


@texture_converter('scale')
def convert_scale(builder, mi_props):
    from mitsuba import ObjectType
    refs = _references(builder, mi_props, ObjectType.Texture)
    if not refs:
        builder.mi_context.log('Scale textures without a nested texture '
                               'are not supported.', 'WARN')
        return None
    source = builder.convert_texture(refs[0])
    if source is None:
        return None
    return _multiply(builder, source, mi_props.get('scale', 1.0))


@texture_converter('mesh_attribute')
def convert_mesh_attribute(builder, mi_props):
    name = mi_props.get('name', '')
    if not name:
        builder.mi_context.log('Mesh attribute textures without a name are '
                               'not supported.', 'WARN')
        return None
    if name.startswith('vertex_'):
        node = builder.node('ShaderNodeVertexColor')
        node.layer_name = name[len('vertex_'):]
    else:
        node = builder.node('ShaderNodeAttribute')
        node.attribute_name = name
    source = node.outputs['Color']
    scale = mi_props.get('scale', 1.0)
    if isinstance(scale, float) and scale != 1.0:
        source = _multiply(builder, source, scale)
    return source


############################
##  Normal and bump maps  ##
############################

def _attach_normal(builder, source, bsdf_socket, chain_input=None):
    '''Link a Normal Map or Bump output into the Normal input of the shader
    node behind bsdf_socket. An already linked Normal input is rerouted
    through chain_input when one is available.'''
    target = bsdf_socket.node.inputs.get('Normal')
    if target is None:
        builder.mi_context.log(
            f'Shader node "{bsdf_socket.node.name}" has no Normal input; '
            'dropping a normal/bump perturbation.', 'WARN')
        return
    if target.is_linked:
        existing = target.links[0].from_socket
        if chain_input is None:
            builder.mi_context.log(
                f'The Normal input of "{bsdf_socket.node.name}" is already '
                'occupied; dropping a normal/bump perturbation.', 'WARN')
            return
        builder.tree.links.remove(target.links[0])
        builder.link(existing, chain_input)
    builder.link(source, target)


def _child_bsdf(builder, mi_props):
    from mitsuba import ObjectType
    children = _references(builder, mi_props, ObjectType.BSDF)
    if len(children) != 1:
        raise ConversionError(
            f'{mi_props.plugin_name()} BSDF expects one child BSDF, got '
            f'{len(children)}')
    return builder.convert_bsdf(builder.child_props(children[0]))


@material_converter('normalmap')
def convert_normalmap(builder, mi_props):
    bsdf_socket = _child_bsdf(builder, mi_props)
    node = builder.node('ShaderNodeNormalMap')
    builder.set_color(node.inputs['Color'], mi_props, 'normalmap',
                      default=(0.5, 0.5, 1.0))
    _attach_normal(builder, node.outputs['Normal'], bsdf_socket)
    return bsdf_socket


@material_converter('bumpmap')
def convert_bumpmap(builder, mi_props):
    from mitsuba import ObjectType
    bsdf_socket = _child_bsdf(builder, mi_props)
    node = builder.node('ShaderNodeBump')
    node.inputs['Distance'].default_value = float(mi_props.get('scale', 1.0))
    refs = _references(builder, mi_props, ObjectType.Texture)
    if refs:
        source = builder.convert_texture(refs[0])
        if source is not None:
            builder.link(source, node.inputs['Height'])
    else:
        builder.mi_context.log('Bumpmap BSDF without a height texture.',
                               'WARN')
    _attach_normal(builder, node.outputs['Normal'], bsdf_socket,
                   chain_input=node.inputs['Normal'])
    return bsdf_socket
