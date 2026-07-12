'''Texture and vector-input converters for material export.

Image data is referenced without side effects on the .blend file: images
that already exist on disk are copied verbatim, everything else (packed,
generated or edited images) is saved through a temporary copy of the
datablock. In render mode no files are written at all; pixel data is handed
to Mitsuba as in-memory bitmaps.

Besides the registered texture converters, this module provides two helpers
for other converters: BSDF converters call `convert_normal_input` on their
Normal input socket to wrap the produced BSDF in normalmap/bumpmap plugins,
and the world exporter calls `convert_environment_texture`.
'''

import os
import shutil

import bpy
from mathutils import Euler, Matrix

from ... import ConversionError
from .. import sanitize_attribute_name
from . import texture_converter
from ._eval import Constant, Texture, eval_color, resolve, trace_source


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


def image_to_bitmap(export_ctx, image):
    '''Convert a Blender image into an in-memory mi.Bitmap. Byte buffers in
    a color space keep their sRGB encoding, which is recorded on the bitmap
    so that Mitsuba linearizes the values like Cycles does; float buffers
    and data color spaces are scene-linear already.'''
    import mitsuba as mi
    import numpy as np

    width, height = image.size
    if width == 0 or height == 0:
        raise ConversionError(f'image "{image.name}" contains no pixel data')
    pixels = np.empty(width * height * image.channels, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    pixels = pixels.reshape(height, width, image.channels)
    # Blender stores rows bottom-up, Mitsuba expects them top-down
    bitmap = mi.Bitmap(np.ascontiguousarray(pixels[::-1]))
    colorspace = image.colorspace_settings.name
    if not image.is_float and colorspace not in _DATA_COLORSPACES:
        if colorspace != 'sRGB':
            export_ctx.log(f'Color space "{colorspace}" of image '
                           f'"{image.name}" is not supported; treating the '
                           'pixel data as sRGB.', 'WARN')
        bitmap.set_srgb_gamma(True)
    return bitmap


def _unique_name(cache, name):
    used = {os.path.basename(path) for path in cache.values()}
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
        return cache[key]

    folder = os.path.join(export_ctx.directory,
                          export_ctx.subfolders['texture'])
    os.makedirs(folder, exist_ok=True)

    source = ''
    if image.filepath_raw:
        source = bpy.path.abspath(image.filepath_raw, library=image.library)
    if source and os.path.isfile(source) and not image.is_dirty \
            and os.path.splitext(source)[1].lower() in _READABLE_EXTS:
        name = _unique_name(cache, os.path.basename(source))
        target = os.path.join(folder, name)
        if os.path.abspath(source) != os.path.abspath(target):
            shutil.copy2(source, target)
    else:
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
            # Copying does not reliably duplicate the pixel buffer of
            # generated or edited images, so transfer it explicitly
            pixels = np.empty(len(image.pixels), dtype=np.float32)
            image.pixels.foreach_get(pixels)
            copy.pixels.foreach_set(pixels)
            copy.filepath_raw = os.path.join(folder, name)
            copy.file_format = file_format
            copy.save()
        finally:
            bpy.data.images.remove(copy)

    path = f"{export_ctx.subfolders['texture']}/{name}"
    cache[key] = path
    return path


######################
##  UV coordinates  ##
######################

# The mesh exporter writes v -> 1 - v; conjugating a Blender UV transform
# with this flip yields the equivalent Mitsuba to_uv transform.
_FLIP = Matrix.Translation((0.0, 1.0, 0.0)) \
    @ Matrix.Diagonal((1.0, -1.0, 1.0, 1.0))


def _is_identity(matrix):
    identity = Matrix.Identity(4)
    return all(abs(matrix[i][j] - identity[i][j]) < 1e-8
               for i in range(4) for j in range(4))


def _to_uv_param(matrix):
    from mitsuba import ScalarTransform4f
    return ScalarTransform4f([list(row) for row in matrix])


def _constant_input(export_ctx, socket, description):
    result = resolve(export_ctx, socket)
    if not isinstance(result, Constant):
        raise ConversionError(f'{description} must be a constant value')
    return result.value


def _mapping_matrix(export_ctx, node):
    location = _constant_input(export_ctx, node.inputs['Location'],
                               f'the location of mapping node "{node.name}"')
    rotation = _constant_input(export_ctx, node.inputs['Rotation'],
                               f'the rotation of mapping node "{node.name}"')
    scale = _constant_input(export_ctx, node.inputs['Scale'],
                            f'the scale of mapping node "{node.name}"')
    if abs(rotation[0]) > 1e-6 or abs(rotation[1]) > 1e-6:
        raise ConversionError(f'mapping node "{node.name}" rotates out of '
                              'the UV plane')
    matrix = Euler(rotation).to_matrix().to_4x4() \
        @ Matrix.Diagonal((*scale, 1.0))
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


def _uv_chain_matrix(export_ctx, socket):
    '''The Blender-UV-space transform of the chain feeding a texture Vector
    input. Only UV sources are supported.'''
    node, source = trace_source(socket)
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
        return _mapping_matrix(export_ctx, node) \
            @ _uv_chain_matrix(export_ctx, node.inputs['Vector'])
    raise ConversionError(f'node "{node.name}" of type {node.type} feeding '
                          'a texture Vector input is not supported')


def _vector_to_uv(export_ctx, node):
    '''The to_uv parameter for a texture node, or None for identity. Chains
    that cannot be converted produce a warning and are ignored.'''
    try:
        matrix = _uv_chain_matrix(export_ctx, node.inputs['Vector'])
    except ConversionError as e:
        export_ctx.log(f'{e}; ignoring the texture mapping of node '
                       f'"{node.name}"', 'WARN')
        return None
    if _is_identity(matrix):
        return None
    return _to_uv_param(_FLIP @ matrix @ _FLIP)


##########################
##  Texture converters  ##
##########################

@texture_converter('TEX_IMAGE')
def convert_image_texture(export_ctx, node, out_socket):
    image = node.image
    if image is None:
        raise ConversionError(f'image texture node "{node.name}" has no '
                              'image')
    if out_socket.name == 'Alpha':
        raise ConversionError(f'the Alpha output of image texture node '
                              f'"{node.name}" is not supported')

    params = {'type': 'bitmap'}
    colorspace = image.colorspace_settings.name
    if export_ctx.render:
        bitmap = image_to_bitmap(export_ctx, image)
        params['bitmap'] = bitmap
        params['raw'] = not bitmap.srgb_gamma()
    else:
        params['filename'] = export_image(export_ctx, image)
        if colorspace in _DATA_COLORSPACES:
            params['raw'] = True
        elif colorspace != 'sRGB':
            export_ctx.log(
                f'Color space "{colorspace}" of image "{image.name}" is not '
                'supported; Mitsuba will interpret the file as sRGB.', 'WARN')

    if node.interpolation == 'Closest':
        params['filter_type'] = 'nearest'
    elif node.interpolation != 'Linear':
        export_ctx.log(f'Interpolation {node.interpolation} of node '
                       f'"{node.name}" is approximated by bilinear '
                       'filtering.', 'WARN')

    if node.extension in ('EXTEND', 'CLIP'):
        params['wrap_mode'] = 'clamp'
        if node.extension == 'CLIP':
            export_ctx.log(f'Extension mode CLIP of node "{node.name}" is '
                           'approximated by clamping.', 'WARN')
    elif node.extension == 'MIRROR':
        params['wrap_mode'] = 'mirror'

    to_uv = _vector_to_uv(export_ctx, node)
    if to_uv is not None:
        params['to_uv'] = to_uv
    return params


@texture_converter('TEX_CHECKER')
def convert_checker_texture(export_ctx, node, out_socket):
    params = {
        'type': 'checkerboard',
        # Once the UV flip is folded into to_uv below, Blender's Color1
        # cells land exactly on Mitsuba's color1 cells
        'color1': eval_color(export_ctx, node.inputs['Color1']),
        'color0': eval_color(export_ctx, node.inputs['Color2']),
    }

    scale_input = resolve(export_ctx, node.inputs['Scale'])
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
        matrix = _uv_chain_matrix(export_ctx, node.inputs['Vector'])
    except ConversionError as e:
        export_ctx.log(f'{e}; ignoring the texture mapping of node '
                       f'"{node.name}"', 'WARN')
        matrix = Matrix.Identity(4)

    # A Mitsuba checkerboard has 2x2 cells per to_uv period, a Blender one
    # has scale x scale cells per UV unit
    checker = Matrix.Diagonal((scale / 2.0, scale / 2.0, 1.0, 1.0)) @ matrix
    params['to_uv'] = _to_uv_param(_FLIP @ checker @ _FLIP)
    return params


@texture_converter('VERTEX_COLOR')
def convert_vertex_color(export_ctx, node, out_socket):
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


###########################
##  Normal and bump map  ##
###########################

def _texture_input(export_ctx, socket, description):
    result = resolve(export_ctx, socket)
    if isinstance(result, Texture):
        return result.params
    if isinstance(result, Constant):
        return None
    raise ConversionError(result.reason)


def _wrap_normalmap(export_ctx, node, bsdf):
    if node.space != 'TANGENT':
        raise ConversionError(f'normal map node "{node.name}" uses '
                              f'{node.space} space; only tangent space is '
                              'supported')
    strength = _constant_input(export_ctx, node.inputs['Strength'],
                               f'the strength of normal map "{node.name}"')
    if abs(strength - 1.0) > 1e-6:
        export_ctx.log(f'Mitsuba normal maps have no strength parameter; '
                       f'ignoring the strength of node "{node.name}".',
                       'WARN')
    texture = _texture_input(export_ctx, node.inputs['Color'],
                             f'normal map node "{node.name}"')
    if texture is None:
        export_ctx.log(f'The color of normal map node "{node.name}" is '
                       'constant and has no effect; ignoring it.', 'WARN')
        return bsdf
    if texture.get('type') == 'bitmap' and not texture.get('raw'):
        export_ctx.log(f'The image of normal map node "{node.name}" should '
                       'use a Non-Color space; interpreting it as raw '
                       'data.', 'WARN')
        texture['raw'] = True
        if 'bitmap' in texture:
            texture['bitmap'].set_srgb_gamma(False)
    return {
        'type': 'normalmap',
        'normalmap': texture,
        'bsdf': bsdf,
    }


def _wrap_bumpmap(export_ctx, node, bsdf):
    # A chained perturbation on the Normal input applies before the bump
    bsdf = convert_normal_input(export_ctx, node.inputs['Normal'], bsdf)
    texture = _texture_input(export_ctx, node.inputs['Height'],
                             f'bump node "{node.name}"')
    if texture is None:
        export_ctx.log(f'The height of bump node "{node.name}" is constant '
                       'and has no effect; ignoring it.', 'WARN')
        return bsdf
    strength = _constant_input(export_ctx, node.inputs['Strength'],
                               f'the strength of bump node "{node.name}"')
    distance = _constant_input(export_ctx, node.inputs['Distance'],
                               f'the distance of bump node "{node.name}"')
    scale = strength * distance
    if node.invert:
        scale = -scale
    return {
        'type': 'bumpmap',
        'texture': texture,
        'scale': scale,
        'bsdf': bsdf,
    }


def convert_normal_input(export_ctx, socket, bsdf):
    '''Wrap a converted BSDF dict in Mitsuba normalmap/bumpmap plugins
    according to what feeds the given Normal input socket. Never raises:
    unsupported input produces a warning and the unwrapped BSDF.'''
    try:
        node, _ = trace_source(socket)
        if node is None:
            return bsdf
        if node.type == 'NORMAL_MAP':
            return _wrap_normalmap(export_ctx, node, bsdf)
        if node.type == 'BUMP':
            return _wrap_bumpmap(export_ctx, node, bsdf)
        raise ConversionError(f'node "{node.name}" of type {node.type} is '
                              'not supported as a normal input')
    except ConversionError as e:
        export_ctx.log(f'{e}; ignoring the normal input of node '
                       f'"{socket.node.name}"', 'WARN')
        return bsdf


###########################
##  Environment texture  ##
###########################

def convert_environment_texture(export_ctx, node):
    '''Convert a TEX_ENVIRONMENT node into a partial envmap emitter dict
    holding the image reference; the world exporter adds scale and
    to_world.'''
    image = node.image
    if image is None:
        raise ConversionError(f'environment texture node "{node.name}" has '
                              'no image')
    if node.projection != 'EQUIRECTANGULAR':
        raise ConversionError(f'projection {node.projection} of environment '
                              f'texture node "{node.name}" is not supported')
    params = {'type': 'envmap'}
    if export_ctx.render:
        # The envmap plugin linearizes according to the bitmap's gamma flag
        params['bitmap'] = image_to_bitmap(export_ctx, image)
    else:
        params['filename'] = export_image(export_ctx, image)
        colorspace = image.colorspace_settings.name
        if colorspace != 'sRGB' and colorspace not in _DATA_COLORSPACES:
            export_ctx.log(
                f'Color space "{colorspace}" of image "{image.name}" is not '
                'supported; Mitsuba will interpret the file as sRGB.', 'WARN')
    return params
