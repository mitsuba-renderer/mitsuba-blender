'''Converters for the diffuse and glossy Cycles BSDF nodes.'''

from . import node_converter
from ._eval import eval_color


@node_converter('BSDF_DIFFUSE')
def convert_diffuse(export_ctx, node):
    roughness = node.inputs['Roughness']
    if roughness.is_linked or roughness.default_value > 0.0:
        export_ctx.log(f'Mitsuba has no rough diffuse BSDF; ignoring the '
                       f'roughness of node "{node.name}".', 'WARN')
    return {
        'type': 'twosided',
        'bsdf': {
            'type': 'diffuse',
            'reflectance': eval_color(export_ctx, node.inputs['Color']),
        },
    }
