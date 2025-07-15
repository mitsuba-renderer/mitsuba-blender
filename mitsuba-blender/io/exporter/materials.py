import bpy
import numpy as np
from mathutils import Matrix
from .export_context import Files

RoughnessMode = {'GGX': 'ggx', 'BECKMANN': 'beckmann', 'ASHIKHMIN_SHIRLEY':'beckmann', 'MULTI_GGX':'ggx'}
#TODO: update when other distributions are supported

def export_texture_node(export_ctx, tex_node):
    params = {
        'type':'bitmap'
    }
    #get the relative path to the copied texture from the full path to the original texture
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

        weight = current_node.inputs['Fac'].default_value#TODO: texture weight

        params = {
            'type': 'blendbsdf',
            'weight': weight
        }
        # add first material
        mat_A = cycles_material_to_dict(export_ctx, mat_I)
        params.update([
            ('bsdf1', mat_A)
        ])

        # add second materials
        mat_B = cycles_material_to_dict(export_ctx, mat_II)
        params.update([
            ('bsdf2', mat_B)
        ])

        return params
    else:#one bsdf, one emitter
        raise NotImplementedError("Mixing a BSDF and an emitter is not supported. Consider using an Add shader instead.")

def convert_principled_materials_cycles(export_ctx, current_node):
    params = {}

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

    base_color = convert_color_texture_node(export_ctx, current_node.inputs['Base Color'])
    specular = current_node.inputs[specular_key].default_value
    if bpy.app.version >= (4, 0, 0):
        specular_tint = convert_color_texture_node(export_ctx, current_node.inputs['Specular Tint'])
    else:
        specular_tint = convert_float_texture_node(export_ctx, current_node.inputs['Specular Tint'])
    specular_trans = convert_float_texture_node(export_ctx, current_node.inputs[transmission_key])
    ior = current_node.inputs['IOR'].default_value
    roughness = convert_float_texture_node(export_ctx, current_node.inputs['Roughness'])
    metallic = convert_float_texture_node(export_ctx, current_node.inputs['Metallic'])
    anisotropic = convert_float_texture_node(export_ctx, current_node.inputs['Anisotropic'])
    sheen = convert_float_texture_node(export_ctx, current_node.inputs[sheen_key])
    if bpy.app.version >= (4, 0, 0):
        sheen_tint = convert_color_texture_node(export_ctx, current_node.inputs['Sheen Tint'])
    else:
        sheen_tint = convert_float_texture_node(export_ctx, current_node.inputs['Sheen Tint'])
    clearcoat = convert_float_texture_node(export_ctx, current_node.inputs[clearcoat_key])
    clearcoat_roughness = convert_float_texture_node(export_ctx, current_node.inputs[clearcoat_roughness_key])

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


#TODO: Add more support for other materials: refraction, transparent, translucent
cycles_converters = {
    'BSDF_PRINCIPLED': convert_principled_materials_cycles,
    "BSDF_DIFFUSE": convert_diffuse_materials_cycles,
    'BSDF_GLOSSY': convert_glossy_materials_cycles,
    'BSDF_GLASS': convert_glass_materials_cycles,
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
