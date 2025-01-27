from ..nodes import *
from .common import *

def convert_glossy_materials_cycles(ctx, current_node, extra):
    roughness = convert_float_texture_node(ctx, current_node.inputs['Roughness'])

    if roughness and current_node.distribution != 'SHARP':
        params = {
            'type': 'roughconductor',
            'alpha': roughness,
            'distribution': RoughnessMode[current_node.distribution],
        }
    else:
        params = { 'type': 'conductor' }

    specular_reflectance = convert_color_texture_node(ctx, current_node.inputs['Color'])

    if specular_reflectance is not None:
        params['specular_reflectance'] = specular_reflectance

    return {
        'type': 'twosided',
        'brdf_0': params
    }