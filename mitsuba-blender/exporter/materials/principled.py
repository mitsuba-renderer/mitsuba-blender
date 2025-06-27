from ..nodes import *
from .common import *

def convert_principled_materials_cycles(ctx, current_node, extra):
    if current_node.subsurface_method != 'RANDOM_WALK':
        logging.warn('Principled BSDF {current_node.subsurface_method} subsurface scattering mode is not supported! Falling back to RANDOM_WALK')

    base_color          = convert_color_texture_node(ctx, current_node.inputs['Base Color'])
    specular            = convert_float_texture_node(ctx, current_node.inputs['Specular IOR Level'])
    specular_tint       = convert_color_texture_node(ctx, current_node.inputs['Specular Tint'])
    specular_trans      = convert_float_texture_node(ctx, current_node.inputs['Transmission Weight'])
    ior                 = convert_float_texture_node(ctx, current_node.inputs['IOR'])
    roughness           = convert_float_texture_node(ctx, current_node.inputs['Roughness'])
    metallic            = convert_float_texture_node(ctx, current_node.inputs['Metallic'])
    anisotropic         = convert_float_texture_node(ctx, current_node.inputs['Anisotropic'])
    clearcoat           = convert_float_texture_node(ctx, current_node.inputs['Coat Weight'])
    clearcoat_roughness = convert_float_texture_node(ctx, current_node.inputs['Coat Roughness'])
    sheen               = convert_float_texture_node(ctx, current_node.inputs['Sheen Weight'])
    sheen_tint          = convert_color_texture_node(ctx, current_node.inputs['Sheen Tint'])
    alpha               = convert_float_texture_node(ctx, current_node.inputs['Alpha'])

    # Undo default roughness transform done by the exporter
    if type(roughness) is float and roughness < 0.0:
        roughness = 0.001

    params = {
        'type'              : 'principled',
        'base_color'        : base_color,
        'spec_tint'         : specular_tint,
        'metallic'          : metallic,
        'anisotropic'       : anisotropic,
        'roughness'         : roughness,
        'sheen'             : sheen,
        'sheen_tint'        : sheen_tint,
        'clearcoat'         : clearcoat,
        'clearcoat_gloss'   : clearcoat_roughness
    }

    # NOTE: Blender uses the 'specular' value for dielectric/metallic reflections and the
    #       'IOR' value for transmission. Mitsuba only has one value for both which can either
    #       be defined by 'specular' or 'eta' ('specular' will be converted into the corresponding
    #       'eta' value by Mitsuba).
    has_transmission = False
    if type(specular_trans) is not float or specular_trans > 0:
        # Export 'eta' and 'spec trans' if the material has a transmission component
        params['spec_trans'] = specular_trans
        params['eta'] = max(ior, 1+1e-3)
        has_transmission = True
    else:
        if type(specular) is float:
            params['specular'] = max(specular, 1+1e-3)

    # Wraps inner BSDF with normal or bump map BSDF
    params = convert_normal_map_node(ctx, current_node.inputs['Normal'], params)

    if type(alpha) is float and alpha < 1.0:
        params = {
            'type'      : 'mask',
            'material'  : params,
            'opacity'   : alpha
        }

    # Only make twosided if we don't have transmission component
    # Causes 2x JITing overhead!
    if not has_transmission:
        params = { 'type': 'twosided', 'nested': params }

    # If the material has emission, then we will redirect it to an area emitter
    emission_strength = convert_float_texture_node(ctx, current_node.inputs['Emission Strength'])
    emission_color    = convert_color_texture_node(ctx, current_node.inputs['Emission Color'])

    emission_color_is_zero = (sum(emission_color['value']) == 0) if emission_color['type'] == 'rgb' else False

    if not emission_color_is_zero and (isinstance(emission_strength, dict) or emission_strength != 0):
        if not isinstance(emission_strength, dict) and emission_color['type'] == 'rgb':
            radiance = ctx.spectrum([
                emission_color['value'][0] * emission_strength,
                emission_color['value'][1] * emission_strength,
                emission_color['value'][2] * emission_strength
            ])
        else:
            radiance = {
                'type': 'mix_rgb',
                'mode': 'multiply',
                'factor': 1.0,
                'color0': emission_strength,
                'color1': emission_color,
            }

        params = [params, { 'type': 'area', 'radiance': radiance }]

    return params
