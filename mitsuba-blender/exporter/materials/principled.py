from ..nodes import *
from .common import *

def convert_principled_materials_cycles(ctx, current_node, extra):
    if current_node.subsurface_method != 'RANDOM_WALK':
        logging.warn('Principled BSDF {current_node.subsurface_method} subsurface scattering mode is not supported! Falling back to RANDOM_WALK')

    if bpy.app.version >= (4, 0, 0):
        specular_key = 'Specular IOR Level'
        transmission_key = 'Transmission Weight'
        sheen_key = 'Sheen Weight'
        clearcoat_key = 'Coat Weight'
        clearcoat_roughness_key = 'Coat Roughness'
    else:
        specular_key = 'Specular'
        transmission_key = 'Transmission'
        sheen_key = 'Sheen'
        clearcoat_key = 'Clearcoat'
        clearcoat_roughness_key = 'Clearcoat Roughness'

    base_color          = convert_color_texture_node(ctx, current_node.inputs['Base Color'])
    specular = current_node.inputs[specular_key].default_value
    if bpy.app.version >= (4, 0, 0):
        specular_tint   = convert_color_texture_node(ctx, current_node.inputs['Specular Tint'])
    else:
        specular_tint   = convert_float_texture_node(ctx, current_node.inputs['Specular Tint'])
    specular_trans      = convert_float_texture_node(ctx, current_node.inputs[transmission_key])
    ior = current_node.inputs['IOR'].default_value
    roughness           = convert_float_texture_node(ctx, current_node.inputs['Roughness'])
    metallic            = convert_float_texture_node(ctx, current_node.inputs['Metallic'])
    anisotropic         = convert_float_texture_node(ctx, current_node.inputs['Anisotropic'])
    clearcoat           = convert_float_texture_node(ctx, current_node.inputs[clearcoat_key])
    clearcoat_roughness = convert_float_texture_node(ctx, current_node.inputs[clearcoat_roughness_key])
    sheen               = convert_float_texture_node(ctx, current_node.inputs[sheen_key])
    if bpy.app.version >= (4, 0, 0):
        sheen_tint      = convert_color_texture_node(ctx, current_node.inputs['Sheen Tint'])
    else:
        sheen_tint      = convert_float_texture_node(ctx, current_node.inputs['Sheen Tint'])

    # Will return None if normals input socket isn't linked
    # normals, normals_meta = convert_normal_map_node(ctx, current_node.inputs['Normal'])

    # Undo default roughness transform done by the exporter
    if type(roughness) is float and roughness < 0.0:
        roughness = 0.001

    params = {
        'type': 'principled',
        'base_color': base_color,
        'spec_tint': specular_tint,
        'spec_trans': specular_trans,
        'metallic': metallic,
        'anisotropic': anisotropic,
        'roughness': roughness,
        'sheen': sheen,
        'sheen_tint': sheen_tint,
        'clearcoat': clearcoat,
        'clearcoat_gloss': clearcoat_roughness
    }

    # NOTE: Blender uses the 'specular' value for dielectric/metallic reflections and the
    #       'IOR' value for transmission. Mitsuba only has one value for both which can either
    #       be defined by 'specular' or 'eta' ('specular' will be converted into the corresponding
    #       'eta' value by Mitsuba).
    if type(specular_trans) is not float or specular_trans > 0:
        # Export 'eta' if the material has a transmission component
        params['eta'] = max(ior, 1+1e-3)
    else:
        if type(specular) is float:
            params['specular'] = max(specular, 1+1e-3)

    params = { 'type': 'twosided', 'nested': params } # Causes 2x JITing overhead!

    # if normals:
    #     if normals_meta['is_bump']:
    #         return {
    #             'type'   : 'bumpmap',
    #             'bumpmap': normals,
    #             'scale'  : normals_meta['distance'],
    #             'params'   : params
    #         }
    #     else:
    #         return {
    #             'type'     : 'normalmap',
    #             'normalmap': normals,
    #             'params'     : params
    #         }

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
