import numpy as np

RoughnessMode = {'GGX': 'ggx', 'BECKMANN': 'beckmann', 'ASHIKHMIN_SHIRLEY':'beckmann', 'MULTI_GGX':'ggx'}
#TODO: update when other distributions are supported

def export_texture_node(export_ctx, tex_node):
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

def convert_float_texture_node(export_ctx, socket):
    params = None

    if socket.is_linked:
        node = socket.links[0].from_node

        if node.type == "TEX_IMAGE":
            params = export_texture_node(export_ctx, node)
        else:
            raise NotImplementedError( "Node type %s is not supported. Only texture nodes are supported for float inputs" % node.type)

    else:
        #roughness values in blender are remapped with a square root
        if 'Roughness' in socket.name:
            params = pow(socket.default_value, 2)
        else:
            params = socket.default_value

    return params

def convert_color_texture_node(export_ctx, socket):
    params = None

    if socket.is_linked:
        node = socket.links[0].from_node

        if node.type == "TEX_IMAGE":
            params = export_texture_node(export_ctx, node)

        elif node.type == "RGB":
            #input rgb node
            params = export_ctx.spectrum(node.color)
        elif node.type == "VERTEX_COLOR":
            params = {
                'type': 'mesh_attribute',
                'name': 'vertex_%s' % node.layer_name
            }
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
    params = {}

    base_color = convert_color_texture_node(export_ctx, current_node.inputs['Base Color'])
    specular = current_node.inputs['Specular IOR Level'].default_value
    specular_tint = convert_color_texture_node(export_ctx, current_node.inputs['Specular Tint'])
    specular_trans = convert_float_texture_node(export_ctx, current_node.inputs['Transmission Weight'])
    ior = current_node.inputs['IOR'].default_value
    roughness = convert_float_texture_node(export_ctx, current_node.inputs['Roughness'])
    metallic = convert_float_texture_node(export_ctx, current_node.inputs['Metallic'])
    anisotropic = convert_float_texture_node(export_ctx, current_node.inputs['Anisotropic'])
    sheen = convert_float_texture_node(export_ctx, current_node.inputs['Sheen Weight'])
    sheen_tint = convert_color_texture_node(export_ctx, current_node.inputs['Sheen Tint'])
    clearcoat = convert_float_texture_node(export_ctx, current_node.inputs['Coat Weight'])
    clearcoat_roughness = convert_float_texture_node(export_ctx, current_node.inputs['Coat Roughness'])

    params.update({
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
    })

    # NOTE: Blender uses the 'specular' value for dielectric/metallic reflections and the
    #       'IOR' value for transmission. Mitsuba only has one value for both which can either
    #       be defined by 'specular' or 'eta' ('specular' will be converted into the corresponding
    #       'eta' value by Mitsuba).
    if type(specular_trans) is not float or specular_trans > 0:
        # Export 'eta' if the material has a transmission component
        params.update({
            'eta': max(ior, 1+1e-3),
        })
        # Transmissive material should not be twosided
        return params
    else:
        # Export 'specular' if the material is only reflective
        params.update({
            'specular': max(specular, 1e-3)
        })
        return two_sided_bsdf(params)

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



#TODO: Add more support for other materials: refraction, transparent, translucent
cycles_converters = {
    'BSDF_PRINCIPLED': convert_principled_materials_cycles,
    "BSDF_DIFFUSE": convert_diffuse_materials_cycles,
    'BSDF_GLOSSY': convert_glossy_materials_cycles,
    'BSDF_GLASS': convert_glass_materials_cycles,
    'BSDF_TRANSPARENT': convert_transparent_materials_cycles,
    'EMISSION': convert_emitter_materials_cycles,
    'MIX_SHADER': convert_mix_materials_cycles,
    'ADD_SHADER': convert_add_materials_cycles,
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
                surface_node = output_node.inputs["Surface"].links[0].from_node
                mat_params = cycles_material_to_dict(export_ctx, surface_node)
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
    export_ctx.exported_mats.add_material(
        {'bsdf': bsdf_id, 'emitter': emitter}, mat_id)

def export_material(export_ctx, material):
    if material is None:
        return

    mat_id = "mat-%s" % material.name
    if export_ctx.data_get(mat_id) is not None \
            or export_ctx.exported_mats.has_mat(mat_id):
        #material was already exported
        return

    # Materials covered by the converter registry take the new path; the
    # remaining node types fall back to the legacy exporter below.
    from ...convert.export import materials as converters
    if converters.has_converter(material):
        result = converters.convert_material(export_ctx, material)
        add_material_to_dict(export_ctx, mat_id, result['bsdf'],
                             result['emitter'])
        return

    mat_params = b_material_to_dict(export_ctx, material)

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
    elif mat_params['type'] == 'area': # Emitter with no bsdf
        add_material_to_dict(export_ctx, mat_id, None, mat_params)
    else: # Usual case
        export_ctx.data_add(mat_params, mat_id)

