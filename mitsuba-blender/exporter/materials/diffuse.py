from ... import logging
from ..nodes import *
from .common import *

def convert_diffuse_materials_cycles(ctx, current_node, extra):
    params = { 'type': 'diffuse' }

    # TODO: Rough diffuse BSDF is currently not supported in Mitsuba
    # roughness = convert_float_texture_node(ctx, current_node.inputs['Roughness'])
    # if roughness:
    #     params = {
    #         'type': 'roughdiffuse',
    #         'alpha': roughness,
    #         'distribution': 'beckmann',
    #     }
    if current_node.inputs['Roughness'].is_linked or current_node.inputs['Roughness'].default_value != 0.0:
        logging.warn("Warning: rough diffuse BSDF is currently not supported in Mitsuba. Ignoring alpha parameter.")

    reflectance = convert_color_texture_node(ctx, current_node.inputs['Color'])
    if reflectance is not None:
        params['reflectance'] = reflectance

    return {
        'type': 'twosided',
        'brdf_0': params
    }