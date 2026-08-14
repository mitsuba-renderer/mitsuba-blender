'''Registry of Blender shader node to Mitsuba material converters.

Converter modules in this package register functions with
@node_converter('<node.type>'). A converter receives (export_ctx, ref),
where `ref` is a resolve.NodeRef pairing the shader node with the group
instance path it was reached through, and returns either a Mitsuba BSDF
dict, or a {'bsdf': dict|None, 'emitter': dict|None} pair when the node
(also) emits light. Converters signal failure by raising ConversionError;
convert_material catches everything and substitutes an error BSDF, so a
broken material never aborts an export.

Texture-producing nodes register with @texture_converter('<node.type>')
instead and are picked up by the socket resolver in resolve.
'''

import copy
import importlib
import pkgutil

from ... import ConversionError
from ....compat import uses_nodes
from ._resolve import (Constant, NodeRef, Texture, Unsupported, eval_color,
                    eval_float, resolve, texture_converter)

_node_converters = {}


def node_converter(*node_types):
    '''Register a converter for the given shader node types (node.type).'''
    def decorator(func):
        for node_type in node_types:
            _node_converters[node_type] = func
        return func
    return decorator


ERROR_COLOR = [1.0, 0.0, 0.3]
ERROR_BSDF = {
    'type': 'twosided',
    'bsdf': {
        'type': 'diffuse',
        'reflectance': {'type': 'rgb', 'value': ERROR_COLOR},
    },
}


def convert_shader_node(export_ctx, ref):
    '''Convert one shader node into a {'bsdf', 'emitter'} pair.'''
    node = ref.node
    converter = _node_converters.get(node.type)
    if converter is None:
        raise ConversionError(f'shader node "{node.name}" of type '
                              f'{node.type} is not supported')
    result = converter(export_ctx, ref)
    if 'type' in result:
        return {'bsdf': result, 'emitter': None}
    return {'bsdf': result.get('bsdf'), 'emitter': result.get('emitter')}


def surface_ref(b_mat):
    '''A NodeRef for the node feeding the Surface input of the material
    output, or None. The Surface node may live inside a node group, so the
    group instance path the trace ended with is kept alongside it.'''
    output = b_mat.node_tree.get_output_node('CYCLES')
    if output is None:
        return None
    node, _, stack = _resolve.trace_source(output.inputs['Surface'])
    return NodeRef(node, stack) if node is not None else None



def convert_material(export_ctx, b_mat):
    '''Convert a Blender material into {'bsdf': dict|None,
    'emitter': dict|None}. Never raises: failures produce a warning and a
    gray diffuse fallback.'''
    try:
        if not uses_nodes(b_mat):
            return {'bsdf': {
                'type': 'diffuse',
                'reflectance': export_ctx.spectrum(b_mat.diffuse_color),
            }, 'emitter': None}
        ref = surface_ref(b_mat)
        if ref is None:
            raise ConversionError('no output node with a linked Surface '
                                  'input')
        return convert_shader_node(export_ctx, ref)
    except Exception as e:
        export_ctx.log(f'Failed to convert material "{b_mat.name}": {e}. '
                       'Exporting an ERROR diffuse fallback.', 'WARN')
        return {'bsdf': copy.deepcopy(ERROR_BSDF), 'emitter': None}

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
    export_ctx.exported_mats[mat_id] = {'bsdf': bsdf_id, 'emitter': emitter}


def export_material(export_ctx, b_mat):
    '''Convert a Blender material and store it in the scene dict, once per
    material name.'''
    if b_mat is None:
        return
    mat_id = f'mat-{b_mat.name}'
    if export_ctx.data_get(mat_id) is not None \
            or mat_id in export_ctx.exported_mats:
        return
    result = convert_material(export_ctx, b_mat)
    add_material_to_dict(export_ctx, mat_id, result['bsdf'],
                         result['emitter'])


# Converter modules register themselves when imported
for _module in pkgutil.iter_modules(__path__):
    if not _module.name.startswith('_'):
        importlib.import_module(f'.{_module.name}', __name__)
