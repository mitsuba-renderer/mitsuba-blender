'''Registry of Blender shader node to Mitsuba material converters.

Converter modules in this package register functions with
@node_converter('<node.type>'). A converter receives (export_ctx, node) and
returns either a Mitsuba BSDF dict, or a {'bsdf': dict|None,
'emitter': dict|None} pair when the node (also) emits light. Converters
signal failure by raising ConversionError; convert_material catches
everything and substitutes a gray diffuse fallback, so a broken material
never aborts an export.

Texture-producing nodes register with @texture_converter('<node.type>')
instead and are picked up by the socket resolver in _eval.
'''

import copy
import importlib
import pkgutil

from ... import ConversionError
from . import _eval
from ._eval import (Constant, Texture, Unsupported, eval_color, eval_float,
                    resolve, texture_converter)

_node_converters = {}


def node_converter(*node_types):
    '''Register a converter for the given shader node types (node.type).'''
    def decorator(func):
        for node_type in node_types:
            _node_converters[node_type] = func
        return func
    return decorator


FALLBACK_BSDF = {
    'type': 'twosided',
    'bsdf': {
        'type': 'diffuse',
        'reflectance': {'type': 'rgb', 'value': [0.5, 0.5, 0.5]},
    },
}


def convert_shader_node(export_ctx, node):
    '''Convert one shader node into a {'bsdf', 'emitter'} pair.'''
    converter = _node_converters.get(node.type)
    if converter is None:
        raise ConversionError(f'shader node "{node.name}" of type '
                              f'{node.type} is not supported')
    result = converter(export_ctx, node)
    if 'type' in result:
        return {'bsdf': result, 'emitter': None}
    return {'bsdf': result.get('bsdf'), 'emitter': result.get('emitter')}


def surface_node(b_mat):
    '''The node feeding the Surface input of the material output, or None.'''
    output = b_mat.node_tree.get_output_node('CYCLES')
    if output is None:
        return None
    node, _ = _eval.trace_source(output.inputs['Surface'])
    return node


def has_converter(b_mat):
    '''Whether this registry takes responsibility for the material.
    Materials without a node tree are left to the caller. Materials without
    a usable surface node are claimed so that convert_material can emit the
    fallback instead of crashing.'''
    if not b_mat.use_nodes or b_mat.node_tree is None:
        return False
    node = surface_node(b_mat)
    return node is None or node.type in _node_converters


def convert_material(export_ctx, b_mat):
    '''Convert a Blender material into {'bsdf': dict|None,
    'emitter': dict|None}. Never raises: failures produce a warning and a
    gray diffuse fallback.'''
    try:
        if not b_mat.use_nodes or b_mat.node_tree is None:
            return {'bsdf': {
                'type': 'diffuse',
                'reflectance': export_ctx.spectrum(b_mat.diffuse_color),
            }, 'emitter': None}
        node = surface_node(b_mat)
        if node is None:
            raise ConversionError('no output node with a linked Surface '
                                  'input')
        return convert_shader_node(export_ctx, node)
    except Exception as e:
        export_ctx.log(f'Failed to convert material "{b_mat.name}": {e}. '
                       'Exporting a gray diffuse fallback.', 'WARN')
        return {'bsdf': copy.deepcopy(FALLBACK_BSDF), 'emitter': None}


def add_material_to_dict(export_ctx, mat_id, bsdf, emitter):
    '''Store a converted BSDF/emitter pair in the scene dict, in the layout
    the shape exporter expects: the BSDF under mat_id, mixed pairs in the
    exported materials cache.'''
    if emitter is None:
        export_ctx.data_add(bsdf, mat_id)
        return
    if bsdf is None:
        # An emitter-only material still needs a BSDF in Mitsuba; a shared
        # black diffuse makes the shape "shadeless"
        if not export_ctx.data_get('empty-emitter-bsdf'):
            export_ctx.data_add({
                'type': 'diffuse',
                'reflectance': export_ctx.spectrum(0.0),
            }, 'empty-emitter-bsdf')
        bsdf_id = 'empty-emitter-bsdf'
    else:
        export_ctx.data_add(bsdf, mat_id)
        bsdf_id = mat_id
    export_ctx.exported_mats.add_material(
        {'bsdf': bsdf_id, 'emitter': emitter}, mat_id)


def export_material(export_ctx, b_mat):
    '''Convert a Blender material and store it in the scene dict, once per
    material name.'''
    if b_mat is None:
        return
    mat_id = f'mat-{b_mat.name}'
    if export_ctx.data_get(mat_id) is not None \
            or export_ctx.exported_mats.has_mat(mat_id):
        return
    result = convert_material(export_ctx, b_mat)
    add_material_to_dict(export_ctx, mat_id, result['bsdf'],
                         result['emitter'])


# Converter modules register themselves when imported
for _module in pkgutil.iter_modules(__path__):
    if not _module.name.startswith('_'):
        importlib.import_module(f'.{_module.name}', __name__)
