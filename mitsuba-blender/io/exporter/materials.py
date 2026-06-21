import bpy
import numpy as np
from mathutils import Matrix
from .export_context import Files

RoughnessMode = {'GGX': 'ggx', 'BECKMANN': 'beckmann', 'ASHIKHMIN_SHIRLEY':'beckmann', 'MULTI_GGX':'ggx'}
#TODO: update when other distributions are supported

VECTORNODE = 'VECTOR'
TEXTURENODE = 'TEXTURE'

def convert_image_texture_node(export_ctx, tex_node):

    params = {
        'type':'bitmap'
    }
    # get the relative path to the copied texture from the full path to the original texture
    params['filename'] = export_ctx.export_texture(tex_node.image)
    #TODO: texture transform (mapping node)
    if tex_node.image.colorspace_settings.name in ['Non-Color', 'Raw', 'Linear']:
        #non color data, tell mitsuba not to apply gamma conversion to it
        params['raw'] = True
    elif tex_node.image.colorspace_settings.name != 'sRGB':
        export_ctx.log("Mitsuba only supports sRGB textures for color data.", 'WARN')

    return params

def convert_vector_node(export_ctx, current_node):
    if current_node.color_tag == TEXTURENODE:
        return convert_texture_node(export_ctx, current_node)
    else:
        raise NotImplementedError("Vector node type %s is not supported." % current_node.type)


def convert_texture_node(export_ctx, current_node):
    params = {}
    if current_node.type == 'TEX_IMAGE':
        params = convert_image_texture_node(export_ctx, current_node)
    else:
        raise NotImplementedError("Texture node type %s is not supported." % current_node.type)
    return params


def convert_float_texture_node(export_ctx, socket):
    params = None

    if socket.is_linked:
        node = socket.links[0].from_node

        if node.type == "TEX_IMAGE":
            params = convert_image_texture_node(export_ctx, node)
        elif node.type == "VALTORGB":
            params = convert_ramp_texture_node(export_ctx, node)
        else:
            raise NotImplementedError( "Node type %s is not supported. Only texture nodes are supported for float inputs" % node.type)

    else:
        #roughness values in blender are remapped with a square root
        if 'Roughness' in socket.name:
            params = pow(socket.default_value, 2)
        else:
            params = socket.default_value

    return params

def convert_mix_texture_node(export_ctx, current_node):
    return {
        'type': 'mix_color',
        'blend_type': current_node.blend_type,
        'clamp_result': current_node.clamp_result,
        'clamp_factor': current_node.clamp_factor,
        'factor': convert_float_texture_node(export_ctx, current_node.inputs['Factor']),
        'a': convert_color_texture_node(export_ctx, current_node.inputs['A']),
        'b': convert_color_texture_node(export_ctx, current_node.inputs['B']),
    }

def convert_ramp_texture_node(export_ctx, current_node):
    fac = convert_float_texture_node(export_ctx, current_node.inputs['Fac'])
    
    color_ramp = current_node.color_ramp
    return {
        'type': 'color_ramp',
        'fac': fac,
        'color_mode': color_ramp.color_mode,
        'interpolation': color_ramp.interpolation,
        'hue_interpolation': color_ramp.hue_interpolation,
        'elements': export_ctx.blender_list_to_str(color_ramp.elements, lambda e: f'{e.alpha} {export_ctx.blender_color_to_str(e.color)} {e.position}')
    }

def convert_color_texture_node(export_ctx, socket):
    params = None

    if socket.is_linked:
        node = socket.links[0].from_node
        if node.type == "TEX_IMAGE":
            params = convert_image_texture_node(export_ctx, node)

        elif node.type == "RGB":
            #input rgb node
            params = export_ctx.spectrum(node.outputs['Color'].default_value)
        elif node.type == "VERTEX_COLOR":
            params = {
                'type': 'mesh_attribute',
                'name': 'vertex_%s' % node.layer_name
            }
        elif node.type == "BRIGHTCONTRAST":
            params = convert_brightcontrast_material_cycles(export_ctx, node)
        elif node.type == 'CURVE_RGB':
            params = convert_rgbcurves_material_cycles(export_ctx, node)
        elif node.type == 'MIX':
            params = convert_mix_texture_node(export_ctx, node)
        elif node.type == 'VALTORGB':
            params = convert_ramp_texture_node(export_ctx, node)
        else:
            raise NotImplementedError("Node type %s is not supported. Only texture & RGB nodes are supported for color inputs" % node.type)

    else:
        params = export_ctx.spectrum(socket.default_value)

    return params

def two_sided_bsdf(bsdf):
    params = {
             'type':'twosided',
             'bsdf': bsdf
    }
    return params

def convert_diffuse_materials_cycles(export_ctx, current_node):
    params = {}
    """
    roughness = convert_float_texture_node(export_ctx, current_node.inputs['Roughness'])
    if roughness:
        params.update({
            'type': 'roughdiffuse',
            'alpha': roughness,
            'distribution': 'beckmann',
        })
    """
    if current_node.inputs['Roughness'].is_linked or current_node.inputs['Roughness'].default_value != 0.0:
        export_ctx.log("Warning: rough diffuse BSDF is currently not supported in Mitsuba. Ignoring alpha parameter.", 'WARN')
    #Rough diffuse BSDF is currently not supported in Mitsuba
    params.update({
        'type': 'diffuse'
    })

    reflectance = convert_color_texture_node(export_ctx, current_node.inputs['Color'])

    if reflectance is not None:
        params.update({
            'reflectance': reflectance,
        })

    return two_sided_bsdf(params)

def convert_glossy_materials_cycles(export_ctx, current_node):
    params = {}

    roughness = convert_float_texture_node(export_ctx, current_node.inputs['Roughness'])

    if roughness and current_node.distribution != 'SHARP':
        params.update({
            'type': 'roughconductor',
            'alpha': roughness,
            'distribution': RoughnessMode[current_node.distribution],
        })
    else:
        params.update({
            'type': 'conductor'
        })

    specular_reflectance = convert_color_texture_node(export_ctx, current_node.inputs['Color'])

    if specular_reflectance is not None:
        params.update({
            'specular_reflectance': specular_reflectance,
        })

    return two_sided_bsdf(params)

def convert_glass_materials_cycles(export_ctx, current_node):
    params = {}

    if current_node.inputs['IOR'].is_linked:
        raise NotImplementedError("Only default IOR value is supported in Mitsuba.")

    ior = current_node.inputs['IOR'].default_value

    roughness = convert_float_texture_node(export_ctx, current_node.inputs['Roughness'])

    if roughness and current_node.distribution != 'SHARP':
        params.update({
            'type': 'roughdielectric',
            'alpha': roughness,
            'distribution': RoughnessMode[current_node.distribution],
        })

    else:
        if ior == 1.0:
            params['type'] = 'thindielectric'
        else:
            params['type'] = 'dielectric'

    params['int_ior'] = ior

    specular_transmittance = convert_color_texture_node(export_ctx, current_node.inputs['Color'])

    if specular_transmittance is not None:
        params.update({
            'specular_transmittance': specular_transmittance,
        })

    return params

def convert_emitter_materials_cycles(export_ctx, current_node):

    if  current_node.inputs["Strength"].is_linked:
        raise NotImplementedError("Only default emitter strength value is supported.")#TODO: value input

    else:
        radiance = current_node.inputs["Strength"].default_value

    if current_node.inputs['Color'].is_linked:
        raise NotImplementedError("Only default emitter color is supported.")#TODO: rgb input

    else:
        radiance = [x * radiance for x in current_node.inputs["Color"].default_value[:]]
        if np.sum(radiance) == 0:
            export_ctx.log("Emitter has zero emission, this will case mitsuba to fail! Ignoring it.", 'WARN')
            return {'type':'diffuse', 'reflectance': export_ctx.spectrum(0)}

    params = {
        'type': 'area',
        'radiance': export_ctx.spectrum(radiance),
    }

    return params

def convert_add_materials_cycles(export_ctx, current_node):
    if not current_node.inputs[0].is_linked or not current_node.inputs[1].is_linked:
        raise NotImplementedError("Add shader is not linked to two materials.")
    mat_I = current_node.inputs[0].links[0].from_node
    mat_II = current_node.inputs[1].links[0].from_node

    if current_node.outputs[0].links[0].to_node.type != 'OUTPUT_MATERIAL':
        raise NotImplementedError("Add Shader is supported only as the final node of the shader (right behind 'Material Output').")
    #TODO: we could support it better to an extent, but it creates lots of degenerate cases, some of which won't work. Is it really worth it?
    elif mat_I.type != 'EMISSION' and mat_II.type != 'EMISSION':
        #Two bsdfs, this is not supported
        raise NotImplementedError("Adding two BSDFs is not supported, consider using a mix shader instead.")
    elif mat_I.type == 'EMISSION' and mat_II.type == 'EMISSION':
        #weight radiances
        #only RGB values for emitter colors are supported for now, so we can do this. It may be broken if we allow textures or spectra in blender
        radiance_I = [float(f) for f in convert_emitter_materials_cycles(export_ctx, mat_I)['radiance']['value'].split(" ")]
        radiance_II = [float(f) for f in convert_emitter_materials_cycles(export_ctx, mat_II)['radiance']['value'].split(" ")]

        sum_radiance = [radiance_I[i] + radiance_II[i] for i in range(3)]
        params = {
            'type': 'area',
            'radiance': export_ctx.spectrum(sum_radiance),
        }
        return params
    else:
        #one emitter, one bsdf
        return [cycles_material_to_dict(export_ctx, mat_I),
                cycles_material_to_dict(export_ctx, mat_II)]

def convert_mix_materials_cycles(export_ctx, current_node):#TODO: test and fix this
    if not current_node.inputs[1].is_linked or not current_node.inputs[2].is_linked:
        raise NotImplementedError("Mix shader is not linked to two materials.")

    mat_I = current_node.inputs[1].links[0].from_node
    mat_II = current_node.inputs[2].links[0].from_node

    if mat_I.type == 'EMISSION' and mat_II.type == 'EMISSION':
        #weight radiances
        #only RGB values for emitter colors are supported for now, so we can do this. It may be broken if we allow textures or spectra in blender
        if current_node.inputs['Fac'].is_linked:#texture weight
            raise NotImplementedError("Only uniform weight is supported for mixing emitters.")
        radiance_I = [float(f) for f in convert_emitter_materials_cycles(export_ctx, mat_I)['radiance']['value'].split(" ")]
        radiance_II = [float(f) for f in convert_emitter_materials_cycles(export_ctx, mat_II)['radiance']['value'].split(" ")]
        w = current_node.inputs['Fac'].default_value
        weighted_radiance = [(1.0-w)*radiance_I[i] + w*radiance_II[i] for i in range(3)]
        params = {
            'type': 'area',
            'radiance': export_ctx.spectrum(weighted_radiance),
        }
        return params
    elif mat_I.type != 'EMISSION' and mat_II.type != 'EMISSION':
        # TODO: When we can process textures in-memory, support exporting mask BSDFs
        weight = convert_color_texture_node(export_ctx, current_node.inputs['Fac'])
        params = {
            'type': 'blendbsdf',
            'weight': weight
        }
        # add first material
        mat_A = cycles_material_to_dict(export_ctx, mat_I)
        params.update([
            ('bsdf1', mat_A)
        ])

        # add second material
        mat_B = cycles_material_to_dict(export_ctx, mat_II)
        params.update([
            ('bsdf2', mat_B)
        ])

        return params
    else:#one bsdf, one emitter
        raise NotImplementedError("Mixing a BSDF and an emitter is not supported. Consider using an Add shader instead.")

def convert_principled_materials_cycles(export_ctx, current_node):
    node_ins = current_node.inputs
    get_color_input = lambda name: convert_color_texture_node(export_ctx, node_ins[name])
    get_float_input = lambda name: convert_float_texture_node(export_ctx, node_ins[name])

    # Subsurface lobe currently not supported
    if node_ins['Subsurface Weight'].is_linked or node_ins['Subsurface Weight'].default_value > 0:
        export_ctx.log("Principled BSDF: subsurface lobe currently is not supported and will be ignored.", 'WARN')

    # Emission lobe currently not supported
    if node_ins['Emission Strength'].is_linked or node_ins['Emission Strength'].default_value > 0:
        export_ctx.log("Principled BSDF: emission lobe currently is not supported and will be ignored.", 'WARN')
    
    # Thin Film lobe currently not supported
    if node_ins['Thin Film Thickness'].is_linked or node_ins['Thin Film Thickness'].default_value > 0:
        export_ctx.log("Principled BSDF: thin film lobe currently is not supported and will be ignored.", 'WARN')
    
    # Tangent direction for specular lobe's anisotropy currently not supported
    if node_ins['Tangent'].is_linked:
        export_ctx.log("Principled BSDF:  lobe currently is not supported and will be ignored.", 'WARN')

    # TODO Specular lobe microfacet distribution selection not supported

    two_sided = True
    transmission = node_ins['Transmission Weight'] 
    if transmission.is_linked or transmission.default_value > 0:
        two_sided = False

    params = {
        'type': 'blender_principled',
        'two_sided': two_sided,

        # Base inputs
        'base_color': get_color_input('Base Color'),
        'roughness': get_float_input('Roughness'),
        'metallic': get_float_input('Metallic'),
        'eta': get_float_input('IOR'),
        'alpha': get_float_input('Alpha'),

        # Diffuse lobe
        'diffuse_roughness': get_float_input('Diffuse Roughness'),

        # Specular lobe 
        'spec_ior_level': get_float_input('Specular IOR Level'),
        'spec_tint': get_color_input('Specular Tint'),
        'anisotropic': get_float_input('Anisotropic'),
        'anisotropic_rot': get_float_input('Anisotropic Rotation'),

        # Transmission lobe
        'transmission': get_float_input('Transmission Weight'),

        # Coat lobe
        'clearcoat': get_float_input('Coat Weight'),
        'clearcoat_roughness': get_float_input('Coat Roughness'),
        'clearcoat_ior': get_float_input('Coat IOR'),
        'clearcoat_tint': get_color_input('Coat Tint'),

        # Sheen lobe
        'sheen': get_float_input('Sheen Weight'),
        'sheen_roughness': get_float_input('Sheen Roughness'),
        'sheen_tint': get_color_input('Sheen Tint'),
    }

    if node_ins['Normal'].is_linked:
        tex_node = node_ins['Normal'].links[0].from_node
        try:
            params.update({'normalmap': convert_vector_node(export_ctx, tex_node)})
        except NotImplementedError as e:
            export_ctx.log(f'Export of texture node \'{tex_node.name}\' failed: {e.args[0]}. Ignoring texture node.', 'WARN')

    if node_ins['Coat Normal'].is_linked:
        tex_node = node_ins['Coat Normal'].links[0].from_node
        try:
            params.update({'clearcoat_normalmap': convert_vector_node(export_ctx, tex_node)})
        except NotImplementedError as e:
            export_ctx.log(f'Export of texture node \'{tex_node.name}\' failed: {e.args[0]}. Ignoring texture node.', 'WARN')

    return params  

def convert_transparent_materials_cycles(export_ctx, current_node):
    if current_node.inputs['Color'].is_linked:
        #TODO: in order to support opacity textures, we need the ability to invert
        # a texture. This will be doable once we convert textures in-memory instead
        # of on-disk (cf PR #121).
        export_ctx.log("Transparent BSDF: opacity textures are currently not supported. Consider using a Mix Shader instead.", 'WARN')
    bl_opacity = current_node.inputs['Color'].default_value
    if min(bl_opacity) == 1.0:
        # Completely transparent, export a null material
        return {'type': 'null'}

    # Invert the opacity value to match Mitsuba's convention
    mi_opacity = [*[1.0 - x for x in bl_opacity[:3]], bl_opacity[3]]
    params = {
        'type': 'mask',
        'opacity': export_ctx.spectrum(mi_opacity),
        'bsdf': {
            'type': 'diffuse',
            'reflectance': export_ctx.spectrum(0.0)
        }
    }

    return params

def convert_translucent_materials_cycles(export_ctx, current_node):
    if current_node.inputs['Normal'].is_linked:
        raise NotImplementedError("Current translucent node does not support normal texture.")
    
    params = {
        'type' : 'translucent',
        'color': convert_color_texture_node(export_ctx, current_node.inputs['Color'])
    }
    return params

def convert_brightcontrast_material_cycles(export_ctx, current_node):
    if not current_node.inputs['Color'].is_linked:
        raise NotImplementedError("Bright contrast node without color input are not supported. Verify that your bright contrast node's inputs are correctly linked.")

    color = convert_color_texture_node(export_ctx, current_node.inputs['Color'])
    
    if current_node.inputs['Bright'].is_linked:
        bright = convert_float_texture_node(export_ctx, current_node.inputs['Bright'])
    else: 
        bright = current_node.inputs['Bright'].default_value 

    if current_node.inputs['Contrast'].is_linked:
        contrast = convert_float_texture_node(export_ctx, current_node.inputs['Contrast'])
    else: 
        contrast = current_node.inputs['Contrast'].default_value

    params = {
        'type': 'brightness_contrast',
        'color': color,
        'brightness': bright,
        'contrast': contrast
    }

    return params

def convert_rgbcurves_material_cycles(export_ctx, current_node):
    if current_node.mapping.tone == 'FILMLIKE':
        raise NotImplementedError("RGB curve node with FILMLIKE tone are not supported. Please use the STANDARD option.")
    
    color = convert_color_texture_node(export_ctx, current_node.inputs['Color'])
    
    if current_node.inputs['Fac'].is_linked:
        fac = convert_float_texture_node(export_ctx, current_node.inputs['Fac'])
    else:
        fac = current_node.inputs['Fac'].default_value

    cmp_to_tuple = lambda p: f'{p.location.x} {p.location.y}'
    curves = current_node.mapping.curves
    param = {
        'type': 'rgb_curve',
        'factor': fac,
        'color': color,
        'points_c': export_ctx.blender_list_to_str(curves[3].points, cmp_to_tuple),
        'points_r': export_ctx.blender_list_to_str(curves[0].points, cmp_to_tuple),
        'points_g': export_ctx.blender_list_to_str(curves[1].points, cmp_to_tuple),
        'points_b': export_ctx.blender_list_to_str(curves[2].points, cmp_to_tuple),
    }
    return param

def convert_refraction_material_cycles(export_ctx, current_node):
    color = convert_color_texture_node(export_ctx, current_node.inputs['Color'])
    ior = convert_float_texture_node(export_ctx, current_node.inputs['IOR'])
    roughness = convert_float_texture_node(export_ctx, current_node.inputs['Roughness'])

    if current_node.inputs['Normal'].is_linked:
        export_ctx.log("Refraction BSDF: Normal mapping is not supported for refraction.", 'WARN')

    return {
        'type': 'refraction',
        'color': color,
        'ior': ior,
        'roughness': roughness
    }

#TODO: Add more support for other materials: refraction, transparent, translucent
cycles_converters = {
    'BSDF_PRINCIPLED': convert_principled_materials_cycles,
    "BSDF_DIFFUSE": convert_diffuse_materials_cycles,
    'BSDF_GLOSSY': convert_glossy_materials_cycles,
    'BSDF_GLASS': convert_glass_materials_cycles,
    'BSDF_TRANSPARENT': convert_transparent_materials_cycles,
    'BSDF_TRANSLUCENT': convert_translucent_materials_cycles,
    'EMISSION': convert_emitter_materials_cycles,
    'MIX_SHADER': convert_mix_materials_cycles,
    'ADD_SHADER': convert_add_materials_cycles,
    'BRIGHTCONTRAST': convert_brightcontrast_material_cycles,
    'CURVE_RGB': convert_rgbcurves_material_cycles,
    'BSDF_REFRACTION': convert_refraction_material_cycles
}

def cycles_material_to_dict(export_ctx, node):
    ''' Converting one material from Blender to Mitsuba dict'''

    if node.type in cycles_converters:
        params = cycles_converters[node.type](export_ctx, node)
    else:
        raise NotImplementedError("Node type: %s is not supported in Mitsuba." % node.type)

    return params

def get_dummy_material(export_ctx):
    return {
        'type': 'diffuse',
        'reflectance': export_ctx.spectrum([1.0, 0.0, 0.3]),
    }

def b_material_to_dict(export_ctx, b_mat):
    ''' Converting one material from Blender / Cycles to Mitsuba'''

    mat_params = {}

    if b_mat.use_nodes:
        try:
            output_node_id = 'Material Output'
            if output_node_id in b_mat.node_tree.nodes:
                output_node = b_mat.node_tree.nodes[output_node_id]
                if output_node.inputs['Surface'].is_linked:
                    surface_node = output_node.inputs["Surface"].links[0].from_node
                    mat_params = cycles_material_to_dict(export_ctx, surface_node)
                else:
                    export_ctx.log(f'Export of material {b_mat.name} failed: Surface input is not linked. Exporting a dummy material instead.', 'WARN')
                    mat_params = get_dummy_material(export_ctx)    
            else:
                export_ctx.log(f'Export of material {b_mat.name} failed: Cannot find material output node. Exporting a dummy material instead.', 'WARN')
                mat_params = get_dummy_material(export_ctx)
        except NotImplementedError as e:
            export_ctx.log(f'Export of material \'{b_mat.name}\' failed: {e.args[0]}. Exporting a dummy material instead.', 'WARN')
            mat_params = get_dummy_material(export_ctx)
    else:
        mat_params = {'type':'diffuse'}
        mat_params['reflectance'] = export_ctx.spectrum(b_mat.diffuse_color)

    return mat_params

def export_material(export_ctx, material):
    mat_params = {}

    if material is None:
        return mat_params

    mat_id = "mat-%s" % material.name

    mat_params = b_material_to_dict(export_ctx, material)

    #TODO: hide emitters
    if export_ctx.data_get(mat_id) is not None:
        #material was already exported
        return

    if isinstance(mat_params, list): # Add/mix shader
        mats = {}
        for mat in mat_params:
            if mat['type'] == 'area': # Emitter
                mats['emitter'] = mat # Directly store the emitter, we don't reference emitters
            else:#bsdf
                mat['id'] = mat_id
                mats['bsdf'] = mat_id
                export_ctx.data_add(mat)
        export_ctx.exported_mats.add_material(mats, mat_id)
    else:
        if mat_params['type'] == 'area': # Emitter with no bsdf
            mats = {}
            # We want the emitter object to be "shadeless", so we need to add it a dummy, empty bsdf, because all objects have a bsdf by default in mitsuba
            if not export_ctx.data_get('empty-emitter-bsdf'): # We only need to add one of this, but we may have multiple emitter materials
                empty_bsdf = {
                    'type':'diffuse',
                    'reflectance':export_ctx.spectrum(0.0), # No interaction with light
                    'id':'empty-emitter-bsdf'
                }
                export_ctx.data_add(empty_bsdf)
            mats['bsdf'] = 'empty-emitter-bsdf'
            mats['emitter'] = mat_params
            export_ctx.exported_mats.add_material(mats, mat_id)

        else: # Usual case
            export_ctx.data_add(mat_params, mat_id)

def convert_world(export_ctx, world, ignore_background):
    """
    convert environment lighting. Constant emitter and envmaps are supported

    Params
    ------

    export_ctx: the export context
    surface_node: the final node of the shader
    ignore_background: whether we want to export blender's default background or not
    """

    params = {}

    if world is None:
        export_ctx.log('No Blender world to export.', 'INFO')
        return

    if world.use_nodes and world.node_tree is not None:
        output_node_id = 'World Output'
        if output_node_id not in world.node_tree.nodes:
            export_ctx.log('Failed to export world: Cannot find world output node.', 'WARN')
            return
        output_node = world.node_tree.nodes[output_node_id]
        if not output_node.inputs["Surface"].is_linked:
            return
        surface_node = output_node.inputs["Surface"].links[0].from_node
        if surface_node.inputs['Strength'].is_linked:
            raise NotImplementedError("Only default emitter strength value is supported.")#TODO: value input
        strength = surface_node.inputs['Strength'].default_value

        if strength == 0: # Don't add an emitter if it emits nothing
            export_ctx.log('Ignoring envmap with zero strength.', 'INFO')
            return

        if surface_node.type in ['BACKGROUND', 'EMISSION']:
            socket = surface_node.inputs["Color"]
            if socket.is_linked:
                color_node = socket.links[0].from_node
                if color_node.type == 'TEX_ENVIRONMENT':
                    params.update({
                        'type': 'envmap',
                        'filename': export_ctx.export_texture(color_node.image),
                        'scale': strength
                    })
                    coordinate_mat = Matrix(((0,0,1,0),(1,0,0,0),(0,1,0,0),(0,0,0,1)))
                    to_world = Matrix()#4x4 Identity
                    if color_node.inputs["Vector"].is_linked:
                        vector_node = color_node.inputs["Vector"].links[0].from_node
                        if vector_node.type != 'MAPPING':
                            raise NotImplementedError("Node: %s is not supported. Only a mapping node is supported" % vector_node.bl_idname)
                        if not vector_node.inputs["Vector"].is_linked:
                            raise NotImplementedError("The node %s should be linked with a Texture coordinate node." % vector_node.bl_idname)
                        coord_node = vector_node.inputs["Vector"].links[0].from_node
                        coord_socket = vector_node.inputs["Vector"].links[0].from_socket
                        if coord_node.type != 'TEX_COORD':
                            raise NotImplementedError("Unsupported node type: %s." % coord_node.bl_idname)
                        if coord_socket.name != 'Generated':
                            raise NotImplementedError("Link should come from 'Generated'.")
                        #only supported node setup for transform
                        if vector_node.vector_type != 'TEXTURE':
                            raise NotImplementedError("Only 'Texture' mapping mode is supported.")
                        if vector_node.inputs["Location"].is_linked or vector_node.inputs["Rotation"].is_linked or vector_node.inputs["Scale"].is_linked:
                            raise NotImplementedError("Transfrom inputs shouldn't be linked.")

                        rotation = vector_node.inputs["Rotation"].default_value.to_matrix()
                        scale = vector_node.inputs["Scale"].default_value
                        location = vector_node.inputs["Location"].default_value
                        for i in range(3):
                            for j in range(3):
                                to_world[i][j] = rotation[i][j]
                            to_world[i][i] *= scale[i]
                            to_world[i][3] = location[i]
                        to_world = to_world
                    #TODO: support other types of mappings (vector, point...)
                    #change default position, apply transform and change coordinates
                    params['to_world'] = export_ctx.transform_matrix(to_world @ coordinate_mat)
                elif color_node.type == 'RGB':
                    color = color_node.color
                else:
                    raise NotImplementedError("Node type %s is not supported. Consider using an environment texture or RGB node instead." % color_node.bl_idname)
            else:
                color = socket.default_value
            if 'type' not in params: # Not an envmap
                radiance = [x * strength for x in color[:3]]
                if ignore_background and radiance == [0.05087608844041824]*3:
                    export_ctx.log("Ignoring Blender's default background...", 'INFO')
                    return
                if np.sum(radiance) == 0:
                    export_ctx.log("Ignoring background emitter with zero emission.", 'INFO')
                    return
                params.update({
                    'type': 'constant',
                    'radiance': export_ctx.spectrum(radiance)
                })
        else:
            raise NotImplementedError("Only Background and Emission nodes are supported as final nodes for World export, got '%s'" % surface_node.name)
    else:
        # Single color field for emission, no nodes
        params.update({
            'type': 'constant',
            'radiance': export_ctx.spectrum(world.color)
        })

    if export_ctx.export_ids:
        export_ctx.data_add(params, "World")
    else:
        export_ctx.data_add(params)

def export_world(export_ctx, world, ignore_background):
    '''
    export_ctx: export context
    world: blender 'world' object
    ignore_background: whether we ignore blender's default grey background or not.
    '''

    try:
        convert_world(export_ctx, world, ignore_background)
    except NotImplementedError as err:
        export_ctx.log("Error while exporting world: %s. Not exporting it." % err.args[0], 'WARN')
