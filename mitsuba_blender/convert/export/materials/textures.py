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


class ImageDataError(ConversionError):
    '''Raised when an image datablock has no usable pixel data.'''


# What Cycles samples wherever an image cannot be loaded
# (TEX_IMAGE_MISSING_* in cycles/kernel/types.h)
_MISSING_IMAGE = (1.0, 0.0, 1.0)
_MISSING_ALPHA = 1.0


def _lazy_load(image):
    '''Touch the first pixel to trigger Blender's lazy load. Images whose
    file is missing stay empty and raise here, which is not an error yet:
    the caller decides after checking `has_data`.'''
    try:
        _ = image.pixels[0]
    except (IndexError, RuntimeError):
        pass


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
            # An earlier export may have left a read-only copy behind, and
            # copying the mode of a read-only source would create one
            if os.path.exists(target):
                os.chmod(target, 0o644)
            shutil.copyfile(source, target)
    else:

        if not image.has_data:
            image.buffers_free()
            _lazy_load(image)

        if not image.has_data:
            for sibling in bpy.data.images:
                if sibling == image:
                    continue
                # Strong match: same file on disk
                if sibling.filepath and sibling.filepath == image.filepath:
                    pass
                # Weak match: same stem, but only if same dimensions and colorspace
                elif (sibling.name.split('.')[0] == image.name.split('.')[0]
                    and sibling.size[:] == image.size[:]
                    and sibling.size[0] > 0
                    and sibling.colorspace_settings.name == image.colorspace_settings.name):
                    pass
                else:
                    continue
                # Try to load the candidate
                if sibling.packed_file and not sibling.has_data:
                    sibling.buffers_free()
                    _lazy_load(sibling)
                if sibling.has_data:
                    export_ctx.log(f'Image "{image.name}" has no data; using'
                        f'sibling "{sibling.name}" instead',
                        'WARN')
                    image = sibling
                    break

        if not image.has_data:
            raise ImageDataError(
                f'image "{image.name}" has no data (file '
                f'"{image.filepath_raw}" is missing or unreadable)')

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
    node = ref.node
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


def _literal(value):
    '''A constant as an expression literal: a parenthesized float, or
    ``rgb(..)`` for a 3-vector. A gray 3-vector becomes a float, since
    ``rgb()`` would force trichromatic evaluation of the expression.'''
    if isinstance(value, (int, float)):
        return f'({float(value)!r})'
    r, g, b = (float(v) for v in tuple(value)[:3])
    if r == g == b:
        return f'({r!r})'
    return f'rgb({r!r}, {g!r}, {b!r})'


def _math(expr, *inputs):
    '''A ``math`` texture dict evaluating ``expr`` over ``inputs``, which are
    floats, 3-tuples, or texture dicts as eval_float/eval_color/eval_vector
    return them. Constants are inlined as literals, so ``in[i]`` in ``expr``
    refers to the i-th input rather than to the i-th texture.'''
    params = {'type': 'math'}
    tex_index = 0
    for i, value in enumerate(inputs):
        if isinstance(value, dict) and value.get('type') == 'rgb':
            literal = _literal(value['value'])
        elif isinstance(value, dict) and value.get('type') == 'srgb' \
                and 'color' in value:
            literal = _literal(value['color'])
        elif isinstance(value, dict):
            literal = f'in[{tex_index}]'
            params[f'in{tex_index}'] = value
            tex_index += 1
        else:
            literal = _literal(value)
        expr = expr.replace(f'in[{i}]', literal)
    params['expr'] = expr
    return params


@texture_converter('TEX_IMAGE')
def convert_image_texture(export_ctx, ref, out_socket):
    '''Convert an image texture node. An image that cannot be loaded is
    replaced by the constant Cycles samples in its place, so that a single
    missing file does not take the whole material down.'''
    try:
        return _convert_image_texture(export_ctx, ref, out_socket)
    except ImageDataError as e:
        export_ctx.log(f'Image texture node "{ref.node.name}": {e}. Using the '
                       'constant Cycles samples for a missing image.', 'WARN')
        if out_socket.name == 'Alpha':
            return export_ctx.spectrum(_MISSING_ALPHA)
        return export_ctx.spectrum(_MISSING_IMAGE)


def _convert_image_texture(export_ctx, ref, out_socket):
    node = ref.node
    image = node.image
    if image is None:
        raise ImageDataError(f'image texture node "{node.name}" has no image')

    params: dict[str, object] = {'type': 'bitmap'}

    if out_socket.name == 'Alpha':
        if image.channels < 4:
            raise ImageDataError(f'image "{image.name}" has no alpha channel')

        import numpy as np
        if not image.has_data:
            _lazy_load(image)
        if not image.has_data:
            raise ImageDataError(f'image "{image.name}" has no data')
        pixels = np.empty(len(image.pixels), dtype=np.float32)
        image.pixels.foreach_get(pixels)
        alpha = pixels.reshape(-1, image.channels)[:, 3]

        alpha_img = bpy.data.images.new(
            f'{image.name}_alpha', image.size[0], image.size[1],
            alpha=False, float_buffer=image.is_float)
        try:
            # Changing the color space frees the pixel buffer of a generated
            # image, so it has to be set before the values are written.
            alpha_img.colorspace_settings.name = 'Non-Color'
            rgba = np.zeros((len(alpha), 4), dtype=np.float32)
            rgba[:, :3] = alpha[:, np.newaxis]
            rgba[:, 3] = 1.0
            alpha_img.pixels.foreach_set(rgba.ravel())
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


# Cycles bakes color ramps and curves into tables of this many entries
# (RAMP_TABLE_SIZE), sampled at i / (N - 1), and interpolates them linearly
RAMP_TABLE_SIZE = 256


def _lut(export_ctx, table, input, kind, **params):
    '''A ``lut`` texture dict over ``table`` of shape (N,) or (N, 3). The
    table is written into the luts subfolder of the export directory as a
    float32 EXR named by its content, so that identical tables share a
    file. An RGB table with identical channels is written as a scalar one,
    which is cheaper to look up.'''
    import hashlib
    import mitsuba as mi
    import numpy as np

    table = np.ascontiguousarray(table, dtype=np.float32)
    if table.ndim == 2 and np.allclose(table[:, :1], table, atol=1e-6):
        table = np.ascontiguousarray(table[:, 0])

    name = f'{kind}_{hashlib.sha1(table.tobytes()).hexdigest()[:12]}.exr'
    folder = os.path.join(export_ctx.directory, export_ctx.LUTS_FOLDER)
    path = os.path.join(folder, name)
    if not os.path.isfile(path):
        os.makedirs(folder, exist_ok=True)
        mi.Bitmap(table[None]).write(path)

    return {'type': 'lut', 'input': input,
            'filename': export_ctx.LUTS_FOLDER + '/' + name, **params}


@texture_converter('VALTORGB')
def convert_color_ramp(export_ctx, ref: NodeRef, out_socket):
    import numpy as np
    node = ref.node
    ramp = node.color_ramp
    n = RAMP_TABLE_SIZE
    alpha = out_socket.name == 'Alpha'
    fac = eval_float(export_ctx, node.inputs['Fac'], stack=ref.stack)

    stops = sorted((e.position, tuple(e.color)) for e in ramp.elements)
    colors = [c[3] if alpha else c[:3] for _, c in stops]

    # Ramps with one or two stops are cheap arithmetic, which is exact and
    # avoids a table file
    if len(stops) == 1:
        value = colors[0]
        if not alpha and any(c < 0.0 or c > 1.0 for c in value):
            return {'type': 'srgb', 'color': list(value), 'unbounded': True}
        return export_ctx.spectrum(value)
    if len(stops) == 2 and stops[0][0] < stops[1][0] and \
            (alpha or ramp.color_mode == 'RGB'):
        p0, p1 = stops[0][0], stops[1][0]
        if ramp.interpolation == 'LINEAR':
            return _math(f'lerp(in[1], in[2], clip((in[0] - {p0!r}) * '
                         f'{1.0 / (p1 - p0)!r}, 0, 1))', fac, *colors)
        if ramp.interpolation == 'CONSTANT':
            return _math(f'in[0] < {p1!r} ? in[1] : in[2]', fac, *colors)

    # ramp.evaluate() implements every interpolation and color mode
    table = np.array([ramp.evaluate(i / (n - 1)) for i in range(n)],
                     dtype=np.float32)
    params = {}
    if ramp.interpolation == 'CONSTANT':
        params['filter_type'] = 'nearest'
    return _lut(export_ctx, table[:, 3] if alpha else table[:, :3], fac,
                'ramp', **params)

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
            params[f'in{tex_index}'] = result.params
            tex_index += 1

    if node.use_clamp:
        params['expr'] = f'clip({params["expr"]}, 0, 1)'

    return params


@texture_converter('HUE_SAT')
def convert_hue_saturation_value(export_ctx: ExportContext, ref: NodeRef, out_socket):
    node = ref.node
    # As in Cycles: shift the hue, scale the saturation (clamped) and the
    # value, clamp the result to be non-negative and blend it in by Fac
    return _math('tmp[0] = rgb_to_hsv(in[0]); '
                 'tmp[1] = hsv_to_rgb(rgb(tmp[0].r + in[1] + 0.5, '
                 'clip(tmp[0].g * in[2], 0, 1), tmp[0].b * in[3])); '
                 'lerp(in[0], max(tmp[1], 0), in[4])',
                 eval_color(export_ctx, node.inputs['Color'], stack=ref.stack),
                 eval_float(export_ctx, node.inputs['Hue'], stack=ref.stack),
                 eval_float(export_ctx, node.inputs['Saturation'], stack=ref.stack),
                 eval_float(export_ctx, node.inputs['Value'], stack=ref.stack),
                 eval_float(export_ctx, node.inputs['Fac'], stack=ref.stack))


@texture_converter('CURVE_RGB')
def convert_rgb_curve(export_ctx: ExportContext, ref : NodeRef, out_socket):
    import numpy as np
    node = ref.node
    mapping = node.mapping
    mapping.update()
    curves = mapping.curves # R, G, B and the combined curve
    n = RAMP_TABLE_SIZE

    # Cycles tabulates the per-channel curves applied after the combined
    # curve over the x range spanned by the control points of all four.
    # Inputs beyond that range are clamped, whereas Blender's default
    # extend mode continues the curves linearly.
    xs = [point.location[0] for curve in curves for point in curve.points]
    min_x, max_x = min(xs), max(xs)
    xs = np.linspace(min_x, max_x, n)
    table = np.empty((n, 3), dtype=np.float32)
    for i, x in enumerate(xs):
        t = mapping.evaluate(curves[3], float(x))
        table[i] = [mapping.evaluate(curves[k], t) for k in range(3)]

    color = eval_color(export_ctx, node.inputs['Color'], stack=ref.stack)
    if np.allclose(table, xs[:, None], atol=1e-6):
        # Untouched curves only clamp the input to their range
        lut = _math(f'clip(in[0], {min_x!r}, {max_x!r})', color)
    else:
        params = {'curve': True}
        if min_x != 0.0:
            params['input_min'] = min_x
        if max_x != 1.0:
            params['input_max'] = max_x
        lut = _lut(export_ctx, table, color, 'curves', **params)

    fac = eval_float(export_ctx, node.inputs['Fac'], stack=ref.stack)
    if fac == 1.0:
        return lut

    params = {'type': 'math', 'in0': color, 'in1': lut}
    if isinstance(fac, dict):
        params['expr'] = 'lerp(in[0], in[1], in[2])'
        params['in2'] = fac
    else:
        params['expr'] = f'lerp(in[0], in[1], {float(fac)})'
    return params


def _socket(sockets, identifier):
    return next(s for s in sockets if s.identifier == identifier)

# Blend modes of the Mix node (Cycles' svm_mix.h) over the inputs a, b and
# the factor t, held in tmp[0]
_MIX_EXPRESSIONS = {
    'MIX':        'lerp(in[0], in[1], tmp[0])',
    'ADD':        'in[0] + tmp[0] * in[1]',
    'MULTIPLY':   'in[0] * (1 - tmp[0] + tmp[0] * in[1])',
    'SUBTRACT':   'in[0] - tmp[0] * in[1]',
    'SCREEN':     '1 - (1 - tmp[0] + tmp[0] * (1 - in[1])) * (1 - in[0])',
    'DIVIDE':     'in[1] != 0 ? (1 - tmp[0]) * in[0] + tmp[0] * in[0] / in[1] : in[0]',
    'DIFFERENCE': '(1 - tmp[0]) * in[0] + tmp[0] * abs(in[0] - in[1])',
    'DARKEN':     'lerp(in[0], min(in[0], in[1]), tmp[0])',
    'LIGHTEN':    'max(in[0], tmp[0] * in[1])',
    'OVERLAY':    'in[0] < 0.5 ? in[0] * (1 - tmp[0] + 2 * tmp[0] * in[1]) '
                  ': 1 - (1 - tmp[0] + 2 * tmp[0] * (1 - in[1])) * (1 - in[0])',
}


@texture_converter('MIX')
def convert_mix(export_ctx: ExportContext, ref : NodeRef, out_socket):
    node = ref.node
    data_type = node.data_type
    factor = eval_float(export_ctx, _socket(node.inputs, 'Factor_Float'), stack=ref.stack)

    if data_type == 'FLOAT':
        # Blend modes apply to colours only; a float mix is a plain lerp
        blend_type = 'MIX'
        a = eval_float(export_ctx, _socket(node.inputs, 'A_Float'), stack=ref.stack)
        b = eval_float(export_ctx, _socket(node.inputs, 'B_Float'), stack=ref.stack)
    elif data_type == 'RGBA':
        blend_type = node.blend_type
        a = eval_color(export_ctx, _socket(node.inputs, 'A_Color'), stack=ref.stack)
        b = eval_color(export_ctx, _socket(node.inputs, 'B_Color'), stack=ref.stack)
    else:
        raise ConversionError(f'Mix node "{node.name}": data type {data_type} is not supported')

    expr = _MIX_EXPRESSIONS.get(blend_type)
    if expr is None:
        raise ConversionError(f'Operation {blend_type} over a MIX node is not supported')
    if node.clamp_result:
        expr = f'clip({expr}, 0, 1)'
    t = 'clip(in[2], 0, 1)' if node.clamp_factor else 'in[2]'
    return _math(f'tmp[0] = {t}; {expr}', a, b, factor)


@texture_converter('INVERT')
def convert_invert(export_ctx: ExportContext, ref : NodeRef, out_socket):
    fac = eval_float(export_ctx, ref.node.inputs['Fac'], stack=ref.stack)
    color = eval_color(export_ctx, ref.node.inputs['Color'], stack=ref.stack)
    return _math('lerp(in[0], (1.0) - in[0], in[1])', color, fac)


@texture_converter('BRIGHTCONTRAST')
def convert_brightness_contrast(export_ctx: ExportContext, ref : NodeRef, out_socket):
    # node_shader_brightness.cc: gain 1 + contrast, offset bright - contrast/2,
    # clamped to zero from below
    return _math('max((1 + in[2]) * in[0] + in[1] - 0.5 * in[2], 0)',
                 eval_color(export_ctx, ref.node.inputs['Color'], stack=ref.stack),
                 eval_float(export_ctx, ref.node.inputs['Bright'], stack=ref.stack),
                 eval_float(export_ctx, ref.node.inputs['Contrast'], stack=ref.stack))


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


# Interpolation of the Map Range node (node_shader_map_range.cc): statements
# turning the linear factor tmp[0] into tmp[2], with the step count in in[5].
# The smoothstep variants clamp the factor regardless of the clamp setting.
_MAP_RANGE_INTERPOLATION = {
    'LINEAR':       'tmp[2] = tmp[0]',
    'STEPPED':      'tmp[2] = in[5] != 0 ? floor(tmp[0] * (in[5] + 1)) / in[5] : 0',
    'SMOOTHSTEP':   'tmp[1] = clip(tmp[0], 0, 1); '
                    'tmp[2] = (3 - 2 * tmp[1]) * tmp[1] * tmp[1]',
    'SMOOTHERSTEP': 'tmp[1] = clip(tmp[0], 0, 1); '
                    'tmp[2] = tmp[1] * tmp[1] * tmp[1] * (tmp[1] * (tmp[1] * 6 - 15) + 10)',
}


@texture_converter('MAP_RANGE')
def convert_map_range(export_ctx: ExportContext, ref : NodeRef, out_socket):
    node = ref.node
    interpolation = _MAP_RANGE_INTERPOLATION.get(node.interpolation_type)
    if interpolation is None:
        raise ConversionError(f'Map Range node "{node.name}": interpolation '
                              f'{node.interpolation_type} is not supported')

    if node.data_type == 'FLOAT':
        ev, names = eval_float, ('Value', 'From Min', 'From Max', 'To Min', 'To Max')
    else:
        ev, names = eval_vector, ('Vector', 'From Min', 'From Max', 'To Min', 'To Max')
    inputs = [ev(export_ctx, node.inputs[name], stack=ref.stack) for name in names]
    steps = next((s for s in node.inputs if s.identifier == 'Steps'), None)
    inputs.append(eval_float(export_ctx, steps, stack=ref.stack) if steps is not None else 4.0)

    # The input is not clamped to the from-range; clamp applies to the result
    # and honours a reversed to-range
    expr = ('tmp[0] = in[2] != in[1] ? (in[0] - in[1]) / (in[2] - in[1]) : 0; '
            f'{interpolation}; '
            'tmp[3] = in[3] + tmp[2] * (in[4] - in[3]); ')
    if node.clamp:
        expr += 'in[4] > in[3] ? clip(tmp[3], in[3], in[4]) : clip(tmp[3], in[4], in[3])'
    else:
        expr += 'tmp[3]'
    return _math(expr, *inputs)


@texture_converter('COMBXYZ')
def convert_combine_xyz(export_ctx: ExportContext, ref: NodeRef, out_socket):
    return _math('rgb(in[0], in[1], in[2])',
                 eval_float(export_ctx, ref.node.inputs['X'], stack=ref.stack),
                 eval_float(export_ctx, ref.node.inputs['Y'], stack=ref.stack),
                 eval_float(export_ctx, ref.node.inputs['Z'], stack=ref.stack))


@texture_converter('SEPXYZ')
def convert_separate_xyz(export_ctx: ExportContext, ref: NodeRef, out_socket):
    channel = {'X': 'r', 'Y': 'g', 'Z': 'b'}[out_socket.identifier]
    return _math(f'in[0].{channel}',
                 eval_vector(export_ctx, ref.node.inputs['Vector'], stack=ref.stack))

@texture_converter('SEPARATE_COLOR')
def convert_separate_color(export_ctx: ExportContext, ref: NodeRef, out_socket):
    node = ref.node
    channel = {'Red': 'r', 'Green': 'g', 'Blue': 'b'}.get(out_socket.name)
    if channel is None:
        raise ConversionError(
            f'output "{out_socket.name}" of Separate Color node '
            f'"{node.name}" is not supported')
    color = {'RGB': 'in[0]', 'HSV': 'rgb_to_hsv(in[0])',
             'HSL': 'rgb_to_hsl(in[0])'}[node.mode]
    return _math(f'{color}.{channel}',
                 eval_color(export_ctx, node.inputs['Color'], stack=ref.stack))


@texture_converter('COMBINE_COLOR')
def convert_combine_color(export_ctx: ExportContext, ref: NodeRef, out_socket):
    node = ref.node
    expr = {'RGB': 'rgb(in[0], in[1], in[2])',
            'HSV': 'hsv_to_rgb(rgb(in[0], in[1], in[2]))',
            'HSL': 'hsl_to_rgb(rgb(in[0], in[1], in[2]))'}[node.mode]
    return _math(expr,
                 eval_float(export_ctx, node.inputs['Red'], stack=ref.stack),
                 eval_float(export_ctx, node.inputs['Green'], stack=ref.stack),
                 eval_float(export_ctx, node.inputs['Blue'], stack=ref.stack))


# Vector Math operations: the expression and the sockets it reads. Scalar
# results are broadcast to all channels.
_VECT_MATH_EXPRESSIONS = {
    'ADD':           ('in[0] + in[1]', 2),
    'SUBTRACT':      ('in[0] - in[1]', 2),
    'MULTIPLY':      ('in[0] * in[1]', 2),
    'DIVIDE':        ('in[1] != 0 ? in[0] / in[1] : 0', 2),
    'MULTIPLY_ADD':  ('fma(in[0], in[1], in[2])', 3),
    'CROSS_PRODUCT': ('rgb(in[0].g * in[1].b - in[0].b * in[1].g, '
                      'in[0].b * in[1].r - in[0].r * in[1].b, '
                      'in[0].r * in[1].g - in[0].g * in[1].r)', 2),
    'DOT_PRODUCT':   ('tmp[0] = in[0] * in[1]; tmp[0].r + tmp[0].g + tmp[0].b', 2),
    'DISTANCE':      ('tmp[0] = (in[0] - in[1]) * (in[0] - in[1]); '
                      'sqrt(tmp[0].r + tmp[0].g + tmp[0].b)', 2),
    'LENGTH':        ('tmp[0] = in[0] * in[0]; sqrt(tmp[0].r + tmp[0].g + tmp[0].b)', 1),
    'SCALE':         ('in[0] * in[1]', 'scale'),
    'NORMALIZE':     ('tmp[0] = in[0] * in[0]; tmp[1] = sqrt(tmp[0].r + tmp[0].g + tmp[0].b); '
                      'tmp[1] > 0 ? in[0] / tmp[1] : 0', 1),
    'ABSOLUTE':      ('abs(in[0])', 1),
    'MINIMUM':       ('min(in[0], in[1])', 2),
    'MAXIMUM':       ('max(in[0], in[1])', 2),
    'FLOOR':         ('floor(in[0])', 1),
    'CEIL':          ('ceil(in[0])', 1),
    'FRACTION':      ('in[0] - floor(in[0])', 1),
    'MODULO':        ('in[1] != 0 ? fmod(in[0], in[1]) : 0', 2),
    'SINE':          ('sin(in[0])', 1),
    'COSINE':        ('cos(in[0])', 1),
    'TANGENT':       ('tan(in[0])', 1),
}


@texture_converter('VECT_MATH')
def convert_vect_math(export_ctx: ExportContext, ref: NodeRef, out_socket):
    node = ref.node
    entry = _VECT_MATH_EXPRESSIONS.get(node.operation)
    if entry is None:
        raise ConversionError(f'Vector math operation {node.operation} of '
                              f'node "{node.name}" is not supported')
    expr, arity = entry
    inputs = [eval_vector(export_ctx, node.inputs['Vector'], stack=ref.stack)]
    if arity == 'scale':
        inputs.append(eval_float(export_ctx, node.inputs['Scale'], stack=ref.stack))
    else:
        for name in ('Vector_001', 'Vector_002')[:arity - 1]:
            inputs.append(eval_vector(export_ctx, node.inputs[name], stack=ref.stack))
    return _math(expr, *inputs)


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

    if texture.get('type') == 'bitmap' and not texture.get('raw'):
        export_ctx.log(f'The image of normal map node "{node.name}" should '
                       'use a Non-Color space; interpreting it as raw '
                       'data.', 'WARN')
        texture['raw'] = True

    params = texture
    if node.inputs['Strength'].is_linked \
            or abs(node.inputs['Strength'].default_value - 1.0) > 1e-6:
        # Cycles (svm_node_normal_map) lerps the shading normal towards the
        # mapped one by the strength, clamped to zero from below, and
        # renormalizes; the normalmap BSDF does the renormalization
        strength = eval_float(export_ctx, node.inputs['Strength'], stack=ref.stack)
        params = _math('tmp[0] = in[0] * 2 - 1; tmp[1] = max(in[1], 0); '
                       'rgb(tmp[0].r * tmp[1], tmp[0].g * tmp[1], '
                       '1 + tmp[1] * (tmp[0].b - 1)) * 0.5 + 0.5',
                       texture, strength)

    return {
        'type': 'normalmap',
        'normalmap': params,
        'bsdf': bsdf,
    }


def _wrap_bumpmap(export_ctx, ref, bsdf):
    node = ref.node
    # A chained perturbation on the Normal input becomes the outer plugin. The
    # bump texture then sees its result as the shading frame of the
    # interaction, which is the input normal that Cycles perturbs.
    texture = _texture_input(export_ctx, node.inputs['Height'], ref.stack)
    if texture is not None:
        bsdf = _bump_bsdf(export_ctx, ref, texture, bsdf)
    else:
        export_ctx.log(f'The height of bump node "{node.name}" is constant '
                       'and has no effect; ignoring it.', 'WARN')
    return convert_normal_input(export_ctx, node.inputs['Normal'], bsdf,
                                ref.stack)


def _bump_bsdf(export_ctx, ref, texture, bsdf):
    node = ref.node
    strength = scalar_from_socket(export_ctx, node.inputs['Strength'], stack=ref.stack)
    distance = scalar_from_socket(export_ctx, node.inputs['Distance'], stack=ref.stack)
    if node.invert:
        distance = -distance
    # The blender_bumpmap texture plugin reproduces the Bump node and returns
    # a tangent space normal. Cycles has no shadowing term.
    bump = {
        'type': 'blender_bumpmap',
        'texture': texture,
        'scale': distance,
        'strength': strength,
    }
    filter_width = node.inputs.get('Filter Width')
    if filter_width is not None:
        bump['filter_width'] = scalar_from_socket(export_ctx, filter_width, stack=ref.stack)
    return {
        'type': 'normalmap',
        'normalmap': bump,
        'use_shadowing_function': False,
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
