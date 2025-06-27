from ..nodes import *
from .common import *

def convert_glass_materials_cycles(ctx, current_node, extra):
    if current_node.inputs['IOR'].is_linked:
        raise NotImplementedError("Only default IOR value is supported in Mitsuba.")

    ior = current_node.inputs['IOR'].default_value

    roughness = convert_float_texture_node(ctx, current_node.inputs['Roughness'])

    if roughness and current_node.distribution != 'SHARP':
        params = {
            'type': 'roughdielectric',
            'alpha': roughness,
            'distribution': RoughnessMode[current_node.distribution],
        }
    else:
        if ior == 1.0:
            params = { 'type': 'thindielectric' }
        else:
            params = { 'type': 'dielectric' }

    params['int_ior'] = ior

    specular_transmittance = convert_color_texture_node(ctx, current_node.inputs['Color'])

    if specular_transmittance is not None:
        params['specular_transmittance'] = specular_transmittance

    return params