'''Registry of Blender shader node to Mitsuba material converters.

Converter modules in this package register functions with
@node_converter('<node.type>'). A converter receives (export_ctx, ref),
where `ref` is a resolve.NodeRef pairing the shader node with the group
instance path it was reached through, and returns either a Mitsuba BSDF
dict, or a {'bsdf': dict, 'emitter': dict|None} pair when the node
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
from ._resolve import (FALLBACK_COLOR, ERROR_COLOR, Constant, NodeRef,
                       Texture, Unsupported, eval_color, eval_float,
                       resolve, texture_converter)

_node_converters = {}


def node_converter(*node_types):
    '''Register a converter for the given shader node types (node.type).'''
    def decorator(func):
        for node_type in node_types:
            _node_converters[node_type] = func
        return func
    return decorator

ERROR_BSDF = {
    'type': 'twosided',
    'bsdf': {
        'type': 'diffuse',
        'reflectance': {'type': 'rgb', 'value': ERROR_COLOR},
    },
}
FALLBACK_BSDF = {
    'type': 'twosided',
    'bsdf': {
        'type': 'diffuse',
        'reflectance': {'type': 'rgb', 'value': FALLBACK_COLOR},
    },
}
BLACK_BSDF = {
    'type': 'twosided',
    'bsdf': {
        'type': 'diffuse',
        'reflectance': {'type': 'rgb', 'value': [0.0, 0.0, 0.0]},
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



def _uses_backfacing(tree, seen=None):
    '''Whether a node tree, or a group used in it, reads the Backfacing
    output of a Geometry node'''
    seen = set() if seen is None else seen
    seen.add(tree.as_pointer())
    for node in tree.nodes:
        if node.bl_idname == 'ShaderNodeNewGeometry' and \
                node.outputs['Backfacing'].is_linked:
            return True
        group = getattr(node, 'node_tree', None) if node.type == 'GROUP' else None
        if group is not None and group.as_pointer() not in seen and \
                _uses_backfacing(group, seen):
            return True
    return False


def _one_sided(bsdf):
    '''The BSDF with its twosided wrappers removed, or None when that is
    not possible'''
    if not isinstance(bsdf, dict):
        return None
    kind = bsdf.get('type')
    if kind == 'twosided' and set(bsdf) == {'type', 'bsdf'}:
        return bsdf['bsdf']
    if kind in ('normalmap', 'bumpmap'):
        inner = _one_sided(bsdf['bsdf'])
        return None if inner is None else {**bsdf, 'bsdf': inner}
    if kind == 'blendbsdf':
        weight = bsdf['weight']
        if weight in (0.0, 1.0):
            return _one_sided(bsdf['bsdf1' if weight == 0.0 else 'bsdf2'])
        bsdf1, bsdf2 = _one_sided(bsdf['bsdf1']), _one_sided(bsdf['bsdf2'])
        if bsdf1 is None or bsdf2 is None:
            return None
        return {**bsdf, 'bsdf1': bsdf1, 'bsdf2': bsdf2}
    return None


def _front_back(front, back):
    '''Combine the BSDFs converted for the front and the back side into a
    twosided BSDF with one nested BSDF per side, or None when Mitsuba
    cannot express the combination'''
    if front == back:
        return front
    if front.get('type') == 'mask' and back.get('type') == 'mask' and \
            front['opacity'] == back['opacity']:
        inner = _front_back(front['bsdf'], back['bsdf'])
        return None if inner is None else {**front, 'bsdf': inner}
    front_1, back_1 = _one_sided(front), _one_sided(back)
    if front_1 is None or back_1 is None:
        return None
    if front_1 == back_1:
        return {'type': 'twosided', 'bsdf': front_1}
    # twosided takes its nested BSDFs in order: front, then back
    return {'type': 'twosided', 'front': front_1, 'back': back_1}


def _convert_sides(export_ctx, b_mat, ref):
    '''Convert a material whose nodes read the Backfacing output once per
    side and combine the results'''
    try:
        export_ctx.backfacing = 0.0
        front = convert_shader_node(export_ctx, ref)
        export_ctx.backfacing = 1.0
        back = convert_shader_node(export_ctx, ref)
    finally:
        export_ctx.backfacing = None
    if front['emitter'] != back['emitter']:
        export_ctx.log(f'Material "{b_mat.name}": the emission differs '
                       'between the front and the back side; exporting '
                       'that of the front side.', 'WARN')
    if front['bsdf'] is None or back['bsdf'] is None:
        bsdf = front['bsdf']
    else:
        bsdf = _front_back(front['bsdf'], back['bsdf'])
    if bsdf is None:
        export_ctx.log(f'Material "{b_mat.name}" differs between the front '
                       'and the back side, which can only be exported for '
                       'opaque reflective BSDFs; exporting the front side.',
                       'WARN')
        bsdf = front['bsdf']
    return {'bsdf': bsdf, 'emitter': front['emitter']}


def convert_material(export_ctx, b_mat):
    '''Convert a Blender material into {'bsdf': dict,
    'emitter': dict|None}. Never raises: failures produce a warning and a
    gray diffuse fallback, an unlinked Surface a black BSDF.'''
    import os
    try:
        if not uses_nodes(b_mat):
            return {'bsdf': {
                'type': 'diffuse',
                'reflectance': export_ctx.spectrum(b_mat.diffuse_color),
            }, 'emitter': None}
        ref = surface_ref(b_mat)
        if ref is None:
            export_ctx.log(f'Material "{b_mat.name}" has no output node with '
                           'a linked Surface input. Exporting a black BSDF, '
                           'which is what Cycles renders.', 'WARN')
            return {'bsdf': copy.deepcopy(BLACK_BSDF), 'emitter': None}
        if _uses_backfacing(b_mat.node_tree):
            return _convert_sides(export_ctx, b_mat, ref)
        return convert_shader_node(export_ctx, ref)
    except Exception as e:
        if export_ctx.strict:
            if os.environ.get('MITSUBA_BLENDER_DEBUG'):
                import traceback
                traceback.print_exc()

            export_ctx.log(f'Failed to convert material "{b_mat.name}": {e}. '
                           'Exporting an ERROR diffuse fallback.', 'WARN')
            return {'bsdf': copy.deepcopy(ERROR_BSDF), 'emitter': None}
        else:
            export_ctx.log(f'Failed to convert material "{b_mat.name}": {e}. '
                           'Exporting a diffuse fallback.', 'WARN')
            return {'bsdf': copy.deepcopy(FALLBACK_BSDF), 'emitter': None}

def add_material_to_dict(export_ctx, mat_id, bsdf, emitter):
    '''Store a converted BSDF/emitter pair in the scene dict, in the layout
    the shape exporter expects: the BSDF under mat_id, mixed pairs in the
    exported materials cache.'''
    export_ctx.data_add(bsdf, mat_id)
    if emitter is None:
        return
    export_ctx.exported_mats[mat_id] = {'bsdf': mat_id, 'emitter': emitter}


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
