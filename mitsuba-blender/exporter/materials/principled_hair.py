from ..nodes import *
from .common import *

def convert_principled_hair_materials_cycles(ctx, current_node, extra):
    import drjit as dr
    d = {
        'type': 'hair',
        'scale_tilt': dr.rad2deg(convert_float_texture_node(ctx, current_node.inputs['Offset'])),
        'int_ior': convert_float_texture_node(ctx, current_node.inputs['IOR']),
        'longitudinal_roughness': convert_float_texture_node(ctx, current_node.inputs['Roughness']),
        'azimuthal_roughness': convert_float_texture_node(ctx, current_node.inputs['Radial Roughness'])
    }

    parametrization = current_node.parametrization
    if parametrization == 'COLOR':
        d['reflectance'] = convert_color_texture_node(ctx, current_node.inputs['Color'])
    elif parametrization == 'ABSORPTION':
        d['sigma_a'] = convert_color_texture_node(ctx, current_node.inputs['Absorption Coefficient'])
    else:
        assert parametrization == 'MELANIN'
        d['eumelanin']     = convert_float_texture_node(ctx, current_node.inputs['Melanin'])
        # d['pheomelanin'] = convert_float_texture_node(ctx, current_node.inputs['Pheomelanin'])

    return d