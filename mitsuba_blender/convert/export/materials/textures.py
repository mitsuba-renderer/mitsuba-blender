'''Texture and vector-input converters for material export.

Image data is referenced without side effects on the .blend file: images
that already exist on disk are copied verbatim, everything else (packed,
generated or edited images) is saved through a temporary copy of the
datablock.

Besides the registered texture converters, this module provides two helpers
for other converters: BSDF converters call `convert_normal_input` on their
Normal input socket to wrap the produced BSDF in normalmap/bumpmap plugins,
and the world exporter calls `convert_environment_texture`.
'''

import os
import shutil

import bpy
from mathutils import Euler, Matrix

from ....io.exporter.export_context import ExportContext

from ... import ConversionError
from .. import sanitize_attribute_name
from . import texture_converter
from ._resolve import (Constant, Texture, NodeRef, eval_color, eval_float,
                    eval_vector, resolve, scalar_from_socket,
                    vector_from_socket, trace_source)


########################
##  Image references  ##
########################

# File types Mitsuba can read directly; anything else is converted on export
_READABLE_EXTS = {'.bmp', '.exr', '.hdr', '.jpeg', '.jpg', '.pfm', '.png',
                  '.ppm', '.tga'}

_SAVE_FORMATS = {
    'BMP': '.bmp',
    'HDR': '.hdr',
    'JPEG': '.jpg',
    'PNG': '.png',
    'OPEN_EXR': '.exr',
    'TARGA': '.tga',
}

# Color spaces whose pixel values Mitsuba should use as-is
_DATA_COLORSPACES = {'Non-Color', 'Raw', 'Linear', 'Linear Rec.709'}

def _unique_name(cache, name):
    used = {os.path.basename(path) for path, _, _ in cache.values()}
    if name not in used:
        return name
    stem, ext = os.path.splitext(name)
    counter = 1
    while f'{stem}-{counter}{ext}' in used:
        counter += 1
    return f'{stem}-{counter}{ext}'


def export_image(export_ctx, image):
    '''Copy or save an image into the textures subfolder of the export
    directory and return its path relative to the scene file. The Blender
    image datablock is never modified.'''
    cache = export_ctx.__dict__.setdefault('exported_images', {})
    key = image.name_full
    if key in cache:
        path, raw, was_dirty = cache[key]
        if was_dirty == image.is_dirty and os.path.isfile(os.path.join(export_ctx.directory, path)):
            return path, raw

    folder = os.path.join(export_ctx.directory,
                          export_ctx.TEXTURES_FOLDER)
    os.makedirs(folder, exist_ok=True)

    source = ''
    raw = False
    if image.filepath_raw:
        source = bpy.path.abspath(image.filepath_raw, library=image.library)
    # Fallback: resolve by basename when the full path doesn't exist
    # (common with scenes authored on Windows and opened on Linux)
    if source and not os.path.isfile(source):
        basename = os.path.basename(source)
        blend_dir = os.path.dirname(bpy.data.filepath)
        if blend_dir:
            for root, dirs, files in os.walk(blend_dir):
                if basename in files:
                    source = os.path.join(root, basename)
                    break

    if source and os.path.isfile(source) and not image.is_dirty \
            and os.path.splitext(source)[1].lower() in _READABLE_EXTS:
        name = _unique_name(cache, os.path.basename(source))
        target = os.path.join(folder, name)
        if os.path.abspath(source) != os.path.abspath(target):
            shutil.copy2(source, target)
    else:
        if not image.has_data:
            stem = image.name.split('.')[0]
            for sibling in bpy.data.images:
                if sibling.name.split('.')[0] == stem and sibling != image:
                    if sibling.packed_file and not sibling.has_data:
                        sibling.buffers_free()
                        _ = sibling.pixels[0]
                    if sibling.has_data:
                        image = sibling
                        break
        if image.packed_file and not image.has_data:
            image.buffers_free()
            _ = image.pixels[0] # for lazy load
            if not image.has_data:
                raise RuntimeError(f'Failed to load packed image "{image.name}"')
        import numpy as np
        file_format = image.file_format
        if file_format not in _SAVE_FORMATS:
            file_format = 'OPEN_EXR' if image.is_float else 'PNG'
        ext = _SAVE_FORMATS[file_format]
        base = image.name if not image.name.lower().endswith(ext) \
            else image.name[:-len(ext)]
        name = _unique_name(cache, f'{base}{ext}')
        copy = image.copy()
        try:
            if image.is_float:
                copy.colorspace_settings.name = 'Non-Color'
                raw = True
            pixels = np.empty(len(image.pixels), dtype=np.float32)
            image.pixels.foreach_get(pixels)
            copy.pixels.foreach_set(pixels)
            copy.filepath_raw = os.path.join(folder, name)
            copy.file_format = file_format
            copy.save()
        finally:
            bpy.data.images.remove(copy)


    path = f'{export_ctx.TEXTURES_FOLDER}/{name}'
    cache[key] = (path, raw, image.is_dirty)
    return path, raw


######################
##  UV coordinates  ##
######################

# Blender addresses the first image row at v = 1, Mitsuba at v = 0
_FLIP = Matrix.Translation((0.0, 1.0, 0.0)) @ Matrix.Diagonal((1.0, -1.0, 1.0, 1.0))


def _to_uv_param(matrix):
    from mitsuba import ScalarTransform4f
    return ScalarTransform4f([list(row) for row in matrix])


def _mapping_matrix(export_ctx, ref):
    node, stack = ref.node, ref.stack
    location = vector_from_socket(export_ctx, ref, node.inputs['Location'])
    rotation = vector_from_socket(export_ctx, ref, node.inputs['Rotation'])
    scale = vector_from_socket(export_ctx, ref, node.inputs['Scale'])

    if abs(rotation[0]) > 1e-6 or abs(rotation[1]) > 1e-6:
        raise ConversionError(f'mapping node "{node.name}" rotates out of '
                              'the UV plane')
    matrix = Euler(rotation).to_matrix().to_4x4() @ Matrix.Diagonal((*scale, 1.0))

    if node.vector_type == 'POINT':
        matrix = Matrix.Translation(location) @ matrix
    elif node.vector_type == 'TEXTURE':
        matrix = Matrix.Translation(location) @ matrix
        if abs(matrix.determinant()) < 1e-12:
            raise ConversionError(f'mapping node "{node.name}" is not '
                                  'invertible')
        matrix = matrix.inverted()
    elif node.vector_type != 'VECTOR':
        raise ConversionError(f'mapping type {node.vector_type} of node '
                              f'"{node.name}" is not supported')
    return matrix


def _uv_chain_matrix(export_ctx, socket, stack):
    '''The Blender-UV-space transform of the chain feeding a texture Vector
    input. Only UV sources are supported.'''
    node, source, node_stack = trace_source(socket, stack)
    if node is None:
        return Matrix.Identity(4)
    if node.type == 'TEX_COORD':
        if source.name != 'UV':
            raise ConversionError(
                f'texture coordinate output "{source.name}" is not '
                'supported; only UV coordinates map to Mitsuba')
        return Matrix.Identity(4)
    if node.type == 'UVMAP':
        if node.uv_map:
            export_ctx.log(
                f'UV map node "{node.name}" selects layer "{node.uv_map}", '
                'but only the active render UV layer is exported.', 'WARN')
        return Matrix.Identity(4)
    if node.type == 'MAPPING':
        if node.vector_type == 'TEXTURE' or node.vector_type == 'POINT':
            return _mapping_matrix(export_ctx,
                                    NodeRef(node, node_stack)) @ _uv_chain_matrix(export_ctx, node.inputs['Vector'],
                                    node_stack)
        # TODO: allow other vector type
        raise ConversionError(f'node "{node.name}" of type MAPPING of vector '
                                f'type "{node.vector_type}" is not supported.'
                                f' Only texture is.')

    raise ConversionError(f'node "{node.name}" of type {node.type} feeding '
                          'a texture Vector input is not supported')


def _vector_to_uv(export_ctx, ref):
    '''The to_uv parameter for a texture node, or None for identity. Chains
    that cannot be converted produce a warning and are ignored.'''
    node = ref.node
    try:
        matrix = _uv_chain_matrix(export_ctx, node.inputs['Vector'], ref.stack)
    except ConversionError as e:
        export_ctx.log(f'{e}; ignoring the texture mapping of node '
                       f'"{node.name}"', 'WARN')
        matrix = Matrix.Identity(4)
    return _to_uv_param(_FLIP @ matrix)


##########################
##  Texture converters  ##
##########################

_ONE_VECTOR_OPS = {'LENGTH', 'SCALE', 'NORMALIZE',
                    'ABSOLUTE', 'FLOOR', 'CEIL',
                    'FRACTION', 'SINE', 'COSINE',
                    'TANGENT'}
_MATH_EXPRESSIONS = {
    # Two-input arithmetic
    'ADD':            'in[0] + in[1]',
    'SUBTRACT':       'in[0] - in[1]',
    'MULTIPLY':       'in[0] * in[1]',
    'DIVIDE':         'in[1] != 0 ? in[0] / in[1] : 0.0',
    'POWER':          'in[0] >= 0 ? pow(in[0], in[1]) : 0.0',
    'LOGARITHM':      'in[0] > 0 && in[1] > 0 ? log(in[0]) / log(in[1]) : 0.0',
    'MODULO':         'in[1] != 0 ? fmod(in[0], in[1]) : 0.0',
    'FLOORED_MODULO': 'in[1] != 0 ? in[0] - floor(in[0] / in[1]) * in[1] : 0.0',
    'MINIMUM':        'min(in[0], in[1])',
    'MAXIMUM':        'max(in[0], in[1])',
    'LESS_THAN':      'in[0] < in[1] ? 1.0 : 0.0',
    'GREATER_THAN':   'in[0] > in[1] ? 1.0 : 0.0',
    'COMPARE':        'abs(in[0] - in[1]) <= in[2] ? 1.0 : 0.0',
    'ARCTAN2':        'atan2(in[0], in[1])',
    'SNAP':           'in[1] != 0 ? floor(in[0] / in[1]) * in[1] : in[0]',

    # One-input
    'SQRT':           'sqrt(max(in[0], 0))',
    'INVERSE_SQRT':   'in[0] > 0 ? rsqrt(in[0]) : 0.0',
    'ABSOLUTE':       'abs(in[0])',
    'NEGATE':         '-in[0]',
    'SIGN':           'in[0] > 0 ? 1.0 : (in[0] < 0 ? -1.0 : 0.0)',
    'ROUND':          'floor(abs(in[0]) + 0.5) * sign(in[0])',
    'FLOOR':          'floor(in[0])',
    'CEIL':           'ceil(in[0])',
    'TRUNC':          'trunc(in[0])',
    'FRACT':          'in[0] - floor(in[0])',
    'SINE':           'sin(in[0])',
    'COSINE':         'cos(in[0])',
    'TANGENT':        'tan(in[0])',
    'ARCSINE':        'asin(clip(in[0], -1, 1))',
    'ARCCOSINE':      'acos(clip(in[0], -1, 1))',
    'ARCTANGENT':     'atan(in[0])',
    'EXPONENT':       'exp(in[0])',
    'RADIANS':        'in[0] * pi / 180.0',
    'DEGREES':        'in[0] * 180.0 / pi',
    'SINH':           'sinh(in[0])',
    'COSH':           'cosh(in[0])',
    'TANH':           'tanh(in[0])',

    # Three-input
    'MULTIPLY_ADD':   'fma(in[0], in[1], in[2])',

    # Complex — need verification
    'PINGPONG':       'tmp[0] = in[1] != 0 ? fmod(in[0], in[1] * 2.0) : 0.0; abs(tmp[0] - in[1])',
    'WRAP':           'tmp[0] = in[1] - in[2]; tmp[0] != 0 ? in[0] - tmp[0] * floor((in[0] - in[2]) / tmp[0]) : in[2]',
    'SMOOTH_MIN':     None,
    'SMOOTH_MAX':     None,
}


def _math(expr, *inputs):
    params = {'type': 'math'}
    tex_index = 0
    final_expr = expr
    for i, value in enumerate(inputs):
        if isinstance(value, dict):
            if value.get('type') == 'rgb':
                v = value['value']
                final_expr = final_expr.replace(
                    f'in[{i}]', f'rgb({v[0]}, {v[1]}, {v[2]})')
            else:
                final_expr = final_expr.replace(f'in[{i}]', f'in[{tex_index}]')
                params[f'input_{tex_index}'] = value
                tex_index += 1
        else:
            final_expr = final_expr.replace(f'in[{i}]', f'({float(value)})')
    params['expr'] = final_expr
    return params


@texture_converter('TEX_IMAGE')
def convert_image_texture(export_ctx, ref, out_socket):
    node = ref.node
    image = node.image
    if image is None:
        raise ConversionError(f'image texture node "{node.name}" has no '
                              'image')

    params: dict[str, object] = {'type': 'bitmap'}

    if out_socket.name == 'Alpha':
        if image.channels < 4:
            raise ConversionError(f'image "{image.name}" has no alpha channel')

        import numpy as np
        pixels = np.empty(len(image.pixels), dtype=np.float32)
        image.pixels.foreach_get(pixels)
        alpha = pixels.reshape(-1, image.channels)[:, 3]

        alpha_img = bpy.data.images.new(
            f'{image.name}_alpha', image.size[0], image.size[1],
            alpha=False, float_buffer=image.is_float)
        try:
            rgba = np.zeros((len(alpha), 4), dtype=np.float32)
            rgba[:, :3] = alpha[:, np.newaxis]
            rgba[:, 3] = 1.0
            alpha_img.pixels.foreach_set(rgba.ravel())
            alpha_img.colorspace_settings.name = 'Non-Color'
            params['filename'], _ = export_image(export_ctx, alpha_img)
        finally:
            bpy.data.images.remove(alpha_img)
        params['raw'] = True

    else:
        colorspace = image.colorspace_settings.name
        params['filename'], raw = export_image(export_ctx, image)

        if raw or colorspace in _DATA_COLORSPACES:
            params['raw'] = True
        elif colorspace != 'sRGB':
            export_ctx.log(
                f'Color space "{colorspace}" of image "{image.name}" '
                'is not supported; Mitsuba will interpret the file '
                'as sRGB.', 'WARN')

    if node.interpolation == 'Closest':
        params['filter_type'] = 'nearest'
    elif node.interpolation != 'Linear':
        export_ctx.log(f'Interpolation {node.interpolation} of node '
                       f'"{node.name}" is approximated by bilinear '
                       'filtering.', 'WARN')

    if node.extension in ('EXTEND', 'CLIP'):
        params['wrap_mode'] = 'clamp'
        if node.extension == 'CLIP':
            export_ctx.log(f'Extension mode CLIP of node "{node.name}" '
                           'is approximated by clamping.', 'WARN')

    elif node.extension == 'MIRROR':
        params['wrap_mode'] = 'mirror'

    to_uv = _vector_to_uv(export_ctx, ref)
    if to_uv is not None:
        params['to_uv'] = to_uv
    return params


@texture_converter('TEX_CHECKER')
def convert_checker_texture(export_ctx, ref, out_socket):
    node = ref.node
    params = {
        'type': 'checkerboard',
        # Once the UV flip is folded into to_uv below, Blender's Color1
        # cells land exactly on Mitsuba's color1 cells
        'color1': eval_color(export_ctx, node.inputs['Color1'],
                             stack=ref.stack),
        'color0': eval_color(export_ctx, node.inputs['Color2'],
                             stack=ref.stack),
    }

    scale_input = resolve(export_ctx, node.inputs['Scale'], stack=ref.stack)
    if isinstance(scale_input, Constant):
        scale = float(scale_input.value)
    else:
        scale = node.inputs['Scale'].default_value
        export_ctx.log(f'The scale of checker texture node "{node.name}" '
                       'must be a constant; using the socket value.', 'WARN')

    if not node.inputs['Vector'].is_linked:
        export_ctx.log(f'Checker texture node "{node.name}" uses generated '
                       'coordinates, which are approximated by UV '
                       'coordinates.', 'WARN')
    try:
        matrix = _uv_chain_matrix(export_ctx, node.inputs['Vector'], ref.stack)
    except ConversionError as e:
        export_ctx.log(f'{e}; ignoring the texture mapping of node '
                       f'"{node.name}"', 'WARN')
        matrix = Matrix.Identity(4)

    # A Mitsuba checkerboard has 2x2 cells per to_uv period, a Blender one
    # has scale x scale cells per UV unit
    checker = Matrix.Diagonal((scale / 2.0, scale / 2.0, 1.0, 1.0)) @ matrix
    params['to_uv'] = _to_uv_param(checker)
    return params


@texture_converter('VERTEX_COLOR')
def convert_vertex_color(export_ctx, ref, out_socket):
    node = ref.node
    if out_socket.name == 'Alpha':
        raise ConversionError(f'the Alpha output of color attribute node '
                              f'"{node.name}" is not supported')
    if not node.layer_name:
        raise ConversionError(f'color attribute node "{node.name}" does not '
                              'name a color attribute')
    return {
        'type': 'mesh_attribute',
        # The mesh exporter sanitizes attribute names the same way, so the
        # reference matches the exported attribute
        'name': f'vertex_{sanitize_attribute_name(node.layer_name)}',
    }


@texture_converter('VALTORGB')
def convert_color_ramp(export_ctx, ref: NodeRef, out_socket):
    node = ref.node
    ramp = node.color_ramp

    params = {
        'type': 'color_ramp',
        'mode': ramp.interpolation.lower(),
        'num_bands': len(ramp.elements),
        'input': eval_float(export_ctx, node.inputs['Fac'], stack=ref.stack)
    }

    for i, element in enumerate(ramp.elements):
        params[f'pos{i}'] = element.position
        params[f'color{i}'] = list(element.color[:3])

    return params

@texture_converter('MATH')
def convert_math(export_ctx, ref, out_socket):
    node = ref.node
    op = node.operation
    expr = _MATH_EXPRESSIONS.get(op)
    if expr is None:
        raise ConversionError(
            f'Math operation {op} of node "{node.name}" is not supported')

    input_sockets = [s for s in node.inputs if s.enabled]

    # First pass: resolve all inputs
    resolved = []
    for socket in input_sockets:
        result = resolve(export_ctx, socket, stack=ref.stack)
        if isinstance(result, (Constant, Texture)):
            resolved.append(result)
        else:
            raise ConversionError(result.reason)

    # Second pass: inline constants, renumber texture inputs
    params = {'type': 'math', 'expr': expr}
    tex_index = 0
    for i, result in enumerate(resolved):
        if isinstance(result, Constant):
            params['expr'] = params['expr'].replace(
                f'in[{i}]', f'({float(result.value)})')
        else:
            if tex_index != i:
                params['expr'] = params['expr'].replace(
                    f'in[{i}]', f'in[{tex_index}]')
            params[f'input_{tex_index}'] = result.params
            tex_index += 1

    if node.use_clamp:
        params['expr'] = f'clip({params["expr"]}, 0, 1)'

    return params


@texture_converter("HUE_SAT")
def convert_hue_saturation_value(export_ctx: ExportContext, ref: NodeRef, out_socket):
    node = ref.node

    params = {
        'type': 'hue_saturation_value',
        'input': eval_color(export_ctx, node.inputs['Color'], stack=ref.stack),
        'hue': eval_float(export_ctx, node.inputs['Hue'], stack=ref.stack),
        'saturation': eval_float(export_ctx, node.inputs['Saturation'], stack=ref.stack),
        'value' : eval_float(export_ctx, node.inputs['Value'], stack=ref.stack),
        'mix' : eval_float(export_ctx, node.inputs['Fac'], stack=ref.stack)
    }
    return params


def _write_curve_table(export_ctx, arr):
    '''Write a sampled curve table beside the scene and return its path.

    The XML writer cannot serialise an in-memory bitmap, so file export
    stores the tables as images like any other texture.
    '''
    import hashlib
    import os
    import mitsuba as mi
    directory = os.path.join(export_ctx.directory, 'textures')
    os.makedirs(directory, exist_ok=True)
    digest = hashlib.sha1(arr.tobytes()).hexdigest()[:12]
    filename = f'curve-{digest}.exr'
    path = os.path.join(directory, filename)
    if not os.path.exists(path):
        mi.Bitmap(arr).write(path)
    return f'textures/{filename}'




@texture_converter('CURVE_RGB')
def convert_rgb_curve(export_ctx: ExportContext, ref : NodeRef, out_socket):
    import numpy as np
    node = ref.node

    params = {
        'type' : 'rgb_curve',
        'fac' : eval_float(export_ctx, node.inputs['Fac'], stack=ref.stack),
        'color' : eval_color(export_ctx, node.inputs['Color'], stack=ref.stack)
    }
    N = 64
    mapping = node.mapping
    mapping.update()


    for i, c in enumerate(['curve_r', 'curve_g', 'curve_b', 'curve_c']):
        curve = mapping.curves[i]
        row = np.array([mapping.evaluate(curve, j / (N - 1)) for j in range(N)], dtype=np.float32)
        arr = np.stack([row, row]).reshape(2, N, 1) # bitmaps need at least 2 x 2

        table = {
            'type': 'bitmap',
            'raw': True,
            'wrap_mode': 'clamp',
            'filename' : _write_curve_table(export_ctx, arr)
        }
        params[c] = table

    return params

def _socket(sockets, identifier):
    return next(s for s in sockets if s.identifier == identifier)

_SUPPORTED = ['MIX', 'ADD', 'MULTIPLY', 'SUBTRACT', 'SCREEN',
              'DIVIDE', 'DIFFERENCE', 'DARKEN', 'LIGHTEN', 'OVERLAY']

@texture_converter('MIX')
def convert_mix(export_ctx: ExportContext, ref : NodeRef, out_socket):
    node = ref.node

    if node.blend_type not in _SUPPORTED:
        raise ConversionError(f'Operation {node.blend_type} over a MIX node is not supported')

    data_type = node.data_type
    params = {
        'type': 'mix',
        'clamp_factor': node.clamp_factor,
        'clamp_result': node.clamp_result,
        'factor': eval_float(export_ctx, _socket(node.inputs, 'Factor_Float'), stack=ref.stack),
    }

    if data_type == 'FLOAT':
        params['blend_type'] = 'MIX'
        params['a'] = eval_float(export_ctx, _socket(node.inputs, 'A_Float'), stack=ref.stack)
        params['b'] = eval_float(export_ctx, _socket(node.inputs, 'B_Float'), stack=ref.stack)
    elif data_type == 'RGBA':
        params['blend_type'] = node.blend_type
        params['a'] = eval_color(export_ctx, _socket(node.inputs, 'A_Color'), stack=ref.stack)
        params['b'] = eval_color(export_ctx, _socket(node.inputs, 'B_Color'), stack=ref.stack)
    else:
        raise ConversionError(f'Mix node "{node.name}": data type {data_type} is not supported')

    return params


@texture_converter('INVERT')
def convert_invert(export_ctx: ExportContext, ref : NodeRef, out_socket):
    fac = eval_float(export_ctx, ref.node.inputs['Fac'], stack=ref.stack)
    color = eval_color(export_ctx, ref.node.inputs['Color'], stack=ref.stack)
    return _math('lerp(in[0], (1.0) - in[0], in[1])', color, fac)


@texture_converter('BRIGHTCONTRAST')
def convert_brightness_contrast(export_ctx: ExportContext, ref : NodeRef, out_socket):
    return {
        'type' : 'brightness_contrast',
        'color' : eval_color(export_ctx, ref.node.inputs['Color'], stack=ref.stack),
        'brightness' : eval_float(export_ctx, ref.node.inputs['Bright'], stack=ref.stack),
        'contrast' : eval_float(export_ctx, ref.node.inputs['Contrast'], stack=ref.stack)
    }


@texture_converter('RGBTOBW')
def convert_rgb_to_bw(export_ctx: ExportContext, ref: NodeRef, out_socket):
    color = eval_color(export_ctx, ref.node.inputs['Color'], stack=ref.stack)
    return _math('luminance(in[0])', color)


@texture_converter('GAMMA')
def convert_gamma(export_ctx: ExportContext, ref: NodeRef, out_socket):
    color = eval_color(export_ctx, ref.node.inputs['Color'], stack=ref.stack)
    gamma = eval_float(export_ctx, ref.node.inputs['Gamma'], stack=ref.stack)
    return _math('in[0] >= 0 ? pow(in[0], in[1]) : 0.0', color, gamma)

@texture_converter('CLAMP')
def convert_clamp(export_ctx: ExportContext, ref: NodeRef, out_socket):
    node, stack = ref.node, ref.stack
    value = eval_float(export_ctx, node.inputs['Value'], stack=stack)
    lo = eval_float(export_ctx, node.inputs['Min'], stack=stack)
    hi = eval_float(export_ctx, node.inputs['Max'], stack=stack)

    if node.clamp_type == 'RANGE':
        lo, hi = (_math('min(in[0], in[1])', lo, hi),
                  _math('max(in[0], in[1])', lo, hi))

    return _math('clip(in[0], in[1], in[2])', value, lo, hi)


@texture_converter('MAP_RANGE')
def convert_map_range(export_ctx: ExportContext, ref : NodeRef, out_socket):
    node = ref.node
    is_float = node.data_type == 'FLOAT'
    params = {
        'type': 'map_range',
        'clamp': node.clamp,
        'vector': not is_float,
        'interpolation_type' : node.interpolation_type,
    }
    if is_float:
        params['input'] = eval_float(export_ctx, node.inputs['Value'], stack=ref.stack)
        params['from_min'] = eval_float(export_ctx, node.inputs['From Min'], stack=ref.stack)
        params['from_max'] = eval_float(export_ctx, node.inputs['From Max'], stack=ref.stack)
        params['to_min'] = eval_float(export_ctx, node.inputs['To Min'], stack=ref.stack)
        params['to_max'] = eval_float(export_ctx, node.inputs['To Max'], stack=ref.stack)
        steps = next((s for s in node.inputs if s.identifier == 'Steps'), None)
        if steps is not None:
            params['steps'] = eval_float(export_ctx, steps, stack=ref.stack)
    else:
        params['input'] = eval_vector(export_ctx, node.inputs['Vector'], stack=ref.stack)
        params['from_min'] = eval_vector(export_ctx, node.inputs['From Min'], stack=ref.stack)
        params['from_max'] = eval_vector(export_ctx, node.inputs['From Max'], stack=ref.stack)
        params['to_min'] = eval_vector(export_ctx, node.inputs['To Min'], stack=ref.stack)
        params['to_max'] = eval_vector(export_ctx, node.inputs['To Max'], stack=ref.stack)
        params['steps'] = eval_vector(export_ctx, node.inputs['Steps'], stack=ref.stack)
    return params


@texture_converter('COMBXYZ')
def convert_combine_xyz(export_ctx: ExportContext, ref: NodeRef, out_socket):
    return {
        'type': 'combine_xyz',
        'x': eval_float(export_ctx, ref.node.inputs['X'], stack=ref.stack),
        'y': eval_float(export_ctx, ref.node.inputs['Y'], stack=ref.stack),
        'z': eval_float(export_ctx, ref.node.inputs['Z'], stack=ref.stack)
    }

@texture_converter('SEPXYZ')
def convert_separate_xyz(export_ctx: ExportContext, ref: NodeRef, out_socket):
    index = {'X': 0, 'Y': 1, 'Z': 2}[out_socket.identifier]
    return {
        'type': 'separate_xyz',
        'index': index,
        'vector': eval_vector(export_ctx, ref.node.inputs['Vector'], stack=ref.stack)
    }

@texture_converter('SEPARATE_COLOR')
def convert_separate_color(export_ctx: ExportContext, ref: NodeRef, out_socket):
    node = ref.node
    color = eval_color(export_ctx, ref.node.inputs['Color'], stack=ref.stack)

    if node.mode == 'RGB':
        channel = {'Red': 'r', 'Green': 'g', 'Blue': 'b'}.get(out_socket.name)
        if channel is None:
            raise ConversionError(
                f'output "{out_socket.name}" of Separate Color node '
                f'"{node.name}" is not supported')
        return _math(f'in[0].{channel}', color)

    channel_map = {'Red': 0, 'Green': 1, 'Blue': 2}
    idx = channel_map.get(out_socket.name)
    if idx is None:
        raise ConversionError(
            f'output "{out_socket.name}" of Separate Color node '
            f'"{node.name}" is not supported')

    return {
        'type': 'separate_color',
        'mode': node.mode,
        'color': color,
        'index': idx,
    }


@texture_converter('COMBINE_COLOR')
def convert_combine_color(export_ctx: ExportContext, ref: NodeRef, out_socket):
    node = ref.node
    if node.mode == 'RGB':
        return _math('rgb(in[0], in[1], in[2])',
                     eval_float(export_ctx, node.inputs['Red'], stack=ref.stack),
                     eval_float(export_ctx, node.inputs['Green'], stack=ref.stack),
                     eval_float(export_ctx, node.inputs['Blue'], stack=ref.stack))
    return {
        'type': 'combine_color',
        'mode' : node.mode,
        'red' : eval_float(export_ctx, node.inputs['Red'], stack=ref.stack),
        'green' : eval_float(export_ctx, node.inputs['Green'], stack=ref.stack),
        'blue' : eval_float(export_ctx, node.inputs['Blue'], stack=ref.stack)
    }


@texture_converter('VECT_MATH')
def convert_vect_math(export_ctx: ExportContext, ref: NodeRef, out_socket):
    op = ref.node.operation
    params = {
        'type': 'vect_math',
        'vec_0': eval_vector(export_ctx, ref.node.inputs['Vector'], stack=ref.stack),
        'op' : op
    }
    if op == 'SCALE':
        params['scale'] = eval_float(export_ctx, ref.node.inputs['Scale'], stack=ref.stack)
    elif op not in _ONE_VECTOR_OPS:
        params['vec_1'] = eval_vector(export_ctx, ref.node.inputs['Vector_001'], stack=ref.stack)

        if op == 'MULTIPLY_ADD':
            params['vec_2'] = eval_vector(export_ctx, ref.node.inputs['Vector_002'], stack=ref.stack)

    return params


@texture_converter('TEX_NOISE')
def convert_tex_noise(export_ctx: ExportContext, ref: NodeRef, out_socket):
    node, stack = ref.node, ref.stack

    if node.noise_dimensions != '3D':
        export_ctx.log(f'Noise node "{node.name}" is {node.noise_dimensions}; '
                       'approximating it with 3D noise.', 'WARN')
    if out_socket.identifier != 'Fac':
        raise ConversionError(f'the {out_socket.name} output of noise node '
                              f'"{node.name}" is not supported')
    params = {
        'type': 'tex_noise',
        'scale': eval_float(export_ctx, node.inputs['Scale'], stack=stack),
        'detail': scalar_from_socket(export_ctx, node.inputs['Detail'], stack=stack),
        'roughness': scalar_from_socket(export_ctx, node.inputs['Roughness'], stack=stack),
        'lacunarity': scalar_from_socket(export_ctx, node.inputs['Lacunarity'], stack=stack),
        'normalize': node.normalize,
    }

    vector = node.inputs['Vector']
    if vector.is_linked:
        params['vector'] = eval_vector(export_ctx, vector, stack=stack)

    distortion = scalar_from_socket(export_ctx, node.inputs['Distortion'], stack=stack)
    if distortion != 0.0:
        export_ctx.log(f'Noise node "{node.name}": distortion is not '
                       'supported; ignoring it.', 'WARN')

    return params

###########################
##  Normal and bump map  ##
###########################

def _texture_input(export_ctx, socket, stack):
    result = resolve(export_ctx, socket, stack=stack)
    if isinstance(result, Texture):
        return result.params
    if isinstance(result, Constant):
        return None
    raise ConversionError(result.reason)


def _wrap_normalmap(export_ctx, ref, bsdf):
    import mitsuba as mi

    node = ref.node
    if node.space != 'TANGENT':
        raise ConversionError(f'normal map node "{node.name}" uses '
                              f'{node.space} space; only tangent space is '
                              'supported')

    texture = _texture_input(export_ctx, node.inputs['Color'], ref.stack)
    if texture is None:
        export_ctx.log(f'The color of normal map node "{node.name}" is '
                       'constant and has no effect; ignoring it.', 'WARN')
        return bsdf


    if texture.get('type') == 'bitmap' and texture.get('filename'):
        img_path = texture['filename']
        if not os.path.isabs(img_path):
            img_path = os.path.join(export_ctx.directory, img_path)

        try:
            bmp = mi.Bitmap(img_path)
            if bmp.channel_count() < 3:
                raise ConversionError(
                    f'normal map node "{node.name}" uses a grayscale image '
                    f'("{os.path.basename(texture["filename"])}"); '
                        'a normal map requires an RGB image')
        except ConversionError:
            raise
        except Exception:
            pass

    strength = eval_float(export_ctx, node.inputs['Strength'], stack=ref.stack)
    params = texture

    use_strength = False
    if node.inputs['Strength'].is_linked \
        or (abs(node.inputs['Strength'].default_value - 1.0) > 1e-6):
        use_strength = True
        params = {
            'type': 'normal_map',
            'texture': texture,
            'strength': strength
        }

    if texture.get('type') == 'bitmap' and not texture.get('raw'):
        export_ctx.log(f'The image of normal map node "{node.name}" should '
                       'use a Non-Color space; interpreting it as raw '
                       'data.', 'WARN')
        if use_strength:
            params['texture']['raw'] = True
        else:
            params['raw'] = True

    return {
        'type': 'normalmap',
        'normalmap': params,
        'bsdf': bsdf,
    }


def _wrap_bumpmap(export_ctx, ref, bsdf):
    import os
    import mitsuba as mi
    node = ref.node
    # A chained perturbation on the Normal input applies before the bump
    bsdf = convert_normal_input(export_ctx, node.inputs['Normal'], bsdf,
                                ref.stack)
    texture = _texture_input(export_ctx, node.inputs['Height'], ref.stack)
    if texture is None:
        export_ctx.log(f'The height of bump node "{node.name}" is constant '
                       'and has no effect; ignoring it.', 'WARN')
        return bsdf
    strength = scalar_from_socket(export_ctx, node.inputs['Strength'], stack=ref.stack)
    distance = scalar_from_socket(export_ctx, node.inputs['Distance'], stack=ref.stack)
    scale = strength * distance
    if node.invert:
        scale = -scale
    return {
        'type': 'bumpmap',
        'texture': texture,
        'scale': scale,
        'bsdf': bsdf,
    }


def convert_normal_input(export_ctx, socket, bsdf, stack=()):
    '''Wrap a converted BSDF dict in Mitsuba normalmap/bumpmap plugins
    according to what feeds the given Normal input socket. Never raises:
    unsupported input produces a warning and the unwrapped BSDF.'''
    try:
        node, _, node_stack = trace_source(socket, stack)
        if node is None:
            return bsdf
        ref = NodeRef(node, node_stack)
        if node.type == 'NORMAL_MAP':
            return _wrap_normalmap(export_ctx, ref, bsdf)
        if node.type == 'BUMP':
            return _wrap_bumpmap(export_ctx, ref, bsdf)
        raise ConversionError(f'node "{node.name}" of type {node.type} is '
                              'not supported as a normal input')
    except ConversionError as e:
        export_ctx.log(f'{e}; ignoring the normal input of node '
                       f'"{socket.node.name}"', 'WARN')
        return bsdf


###########################
##  Environment texture  ##
###########################

def convert_environment_texture(export_ctx, ref):
    '''Convert a TEX_ENVIRONMENT node into a partial envmap emitter dict
    holding the image reference; the world exporter adds scale and
    to_world.'''
    node = ref.node
    image = node.image
    if image is None:
        raise ConversionError(f'environment texture node "{node.name}" has '
                              'no image')
    if node.projection != 'EQUIRECTANGULAR':
        raise ConversionError(f'projection {node.projection} of environment '
                              f'texture node "{node.name}" is not supported')
    params = {'type': 'envmap'}
    params['filename'], _ = export_image(export_ctx, image)

    colorspace = image.colorspace_settings.name
    if colorspace != 'sRGB' and colorspace not in _DATA_COLORSPACES:
        export_ctx.log(
            f'Color space "{colorspace}" of image "{image.name}" is not '
            'supported; Mitsuba will interpret the file as sRGB.', 'WARN')
    return params
