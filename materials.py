from numpy import pi
from mathutils import Matrix

def linear_to_srgb(x):
    if x > 0.0031308:
        x = 1.055 * pow(x, 0.416) - 0.055
    else:
        x = 12.92 * x
    return x

def srgb_to_linear(x):
    if x > 0.04045:
        x = pow((x+0.055)/1.055, 2.4)
    else:
        x = x / 12.92
    return x

RoughnessMode = {'GGX': 'ggx', 'BECKMANN': 'beckmann', 'ASHIKHMIN_SHIRLEY':'beckmann', 'MULTI_GGX':'ggx'}
#TODO: update when other distributions are supported

def export_texture_node(export_ctx, tex_node):
    params = {
        'plugin':'texture',
        'type':'bitmap'
    }
    params['filename'] = tex_node.image.filepath_from_user()#abs path to texture
    #TODO: texture transform (mapping node)
    #TODO: save textures in the scene directory
    flip_tex = Matrix(((1,0,0,0),
                       (0,-1,0,0),
                       (0,0,1,0),
                       (0,0,0,1)))
    params['to_uv'] = export_ctx.transform_matrix(flip_tex)
    if tex_node.image.colorspace_settings.name in ['Non-Color', 'Raw']:
        #non color data, tell mitsuba not to apply gamma conversion to it
        params['raw'] = True
    elif tex_node.image.colorspace_settings.name != 'sRGB':
        print("Warning: Mitsuba only supports sRGB textures for color data.")

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
        if socket.name == 'Roughness':#roughness values in blender are remapped with a square root
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
            params = export_ctx.spectrum(node.color, 'rgb')
        
        else:
            raise NotImplementedError("Node type %s is not supported. Only texture & RGB nodes are supported for color inputs" % node.type)

    else:
        params = export_ctx.spectrum(socket.default_value)

    return params

def two_sided_bsdf(bsdf):
    params = {
             'plugin':'bsdf',
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
        print("Warning: rough diffuse BSDF is currently not supported in Mitsuba 2. Ignoring alpha parameter.")
    #Rough diffuse BSDF is currently not supported in Mitsuba
    params.update({
        'plugin': 'bsdf',
        'type': 'diffuse'
    })

    reflectance = convert_color_texture_node(export_ctx, current_node.inputs['Color'])

    if reflectance is not None:
        params.update({
            'reflectance': reflectance,
        })

    return two_sided_bsdf(params)

def convert_glossy_materials_cycles(export_ctx, current_node):
    params = {'plugin':'bsdf'}

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
    params = {'plugin': 'bsdf'}

    if current_node.inputs['IOR'].is_linked:
        raise NotImplementedError("Only default IOR value is supported in Mitsuba 2.")

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
        radiance = current_node.inputs["Strength"].default_value#TODO: fix this

    if current_node.inputs['Color'].is_linked:
        raise NotImplementedError("Only default emitter color is supported.")#TODO: rgb input

    else:
        radiance = [x * radiance for x in current_node.inputs["Color"].default_value[:]]

    params = {
        'plugin': 'emitter',
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
            'plugin': 'emitter',
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
            'plugin': 'emitter',
            'type': 'area',
            'radiance': export_ctx.spectrum(weighted_radiance),
        }
        return params

    elif mat_I.type != 'EMISSION' and mat_II.type != 'EMISSION':

        weight = current_node.inputs['Fac'].default_value#TODO: texture weight

        params = {
            'plugin': 'bsdf',
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

#TODO: Add more support for other materials: refraction, transparent, translucent, principled
cycles_converters = {
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
        raise NotImplementedError("Node type: %s is not supported in Mitsuba 2." % node.type)

    return params

def b_material_to_dict(export_ctx, b_mat):
    ''' Converting one material from Blender / Cycles to Mitsuba'''

    mat_params = {}

    if b_mat.use_nodes:
        try:
            output_node = b_mat.node_tree.nodes["Material Output"]
            surface_node = output_node.inputs["Surface"].links[0].from_node
            mat_params = cycles_material_to_dict(export_ctx, surface_node)

        except NotImplementedError as err:
            print("Export of material %s failed : %s Exporting a dummy texture instead." % (b_mat.name, err.args[0]))
            mat_params = {'plugin':'bsdf', 'type':'diffuse'}
            mat_params['reflectance'] = export_ctx.spectrum([1.0,0.0,0.3], 'rgb')

    else:
        mat_params = {'plugin':'bsdf', 'type':'diffuse'}
        mat_params['reflectance'] = export_ctx.spectrum(b_mat.diffuse_color, 'rgb')

    return mat_params

def export_material(export_ctx, material):
    mat_params = {}

    if material is None:
        return mat_params

    name = material.name

    mat_params = b_material_to_dict(export_ctx, material)

    #TODO: hide emitters
    #TODO: don't export unused materials

    if isinstance(mat_params, list):#Add/mix shader
        mats = {}
        for mat in mat_params:
            if mat['plugin'] == 'bsdf':
                mat['id'] = name#only bsdfs need IDs for referencing
                mats['bsdf'] = name
                export_ctx.data_add(mat)
            else:#emitter
                mats['emitter'] = mat#directly store the emitter, we don't reference emitters
        export_ctx.mixed_mats.add_material(mats, name)
    else:
        if mat_params['plugin'] == 'bsdf':#usual case
            mat_params['id'] = name
            export_ctx.data_add(mat_params)
        else:#emitter with no bsdf
            mats = {}
            #we want the emitter object to be "shadeless", so we need to add it a dummy, empty bsdf, because all objects have a bsdf by default in mitsuba 2
            if 'empty-emitter-bsdf' not in export_ctx.scene_data:#we only need to add one of this, but we may have multiple emitter materials
                empty_bsdf = {
                    'plugin':'bsdf',
                    'type':'diffuse',
                    'reflectance':export_ctx.spectrum(0),#no interaction with light
                    'id':'empty-emitter-bsdf'
                }
                export_ctx.data_add(empty_bsdf)
            mats['bsdf'] = 'empty-emitter-bsdf'
            mats['emitter'] = mat_params
            export_ctx.mixed_mats.add_material(mats, name)
    """
    if mat_params['plugin']=='bsdf' and mat_params['type'] != 'null':
        bsdf_params = OrderedDict([('id', '%s-bsdf' % name)])
        bsdf_params.update(mat_params['bsdf'])
        export_ctx.data_add(bsdf_params)
        mat_params.update({'bsdf': {'type': 'ref', 'id': '%s-bsdf' % name}})

    if 'interior' in mat_params:
        interior_params = {'id': '%s-medium' % name}
        interior_params.update(mat_params['interior'])

        if interior_params['type'] == 'ref':
            mat_params.update({'interior': interior_params})

        else:
            export_ctx.data_add(interior_params)
            mat_params.update({'interior': {'type': 'ref', 'id': '%s-medium' % name}})
    return mat_params
    """

def convert_world(export_ctx, surface_node):
    """
    convert environment lighting. Constant emitter and envmaps are supported
    """
    params = {
            'plugin':'emitter',
            }
    if surface_node.inputs['Strength'].is_linked:
        raise NotImplementedError("Only default emitter strength value is supported.")#TODO: value input
    strength = surface_node.inputs['Strength'].default_value

    if surface_node.type in ['BACKGROUND', 'EMISSION']:
        socket = surface_node.inputs["Color"]
        if socket.is_linked:
            color_node = socket.links[0].from_node
            if color_node.type == 'TEX_ENVIRONMENT':
                params.update({
                    'type': 'envmap',
                    'filename': color_node.image.filepath_from_user(),
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
                params['to_world'] = export_ctx.transform_matrix(to_world @ coordinate_mat)
            elif color_node.type == 'RGB':
                color = color_node.color
        else:
            color = socket.default_value
        if 'type' not in params:
            radiance = [x * strength for x in color[:]]
            params.update({
                'type': 'constant',
                'radiance': export_ctx.spectrum(radiance)
            })

    else:
        raise NotImplementedError("Node type %s is not supported" % surface_node.type)

    return params

def export_world(export_ctx, world):

    output_node = world.node_tree.nodes['World Output']
    if not output_node.inputs["Surface"].is_linked:
        return
    surface_node = output_node.inputs["Surface"].links[0].from_node
    try:
        params = convert_world(export_ctx, surface_node)
        export_ctx.data_add(params)
    except NotImplementedError as err:
        print("Error while exporting world: %s. Not exporting it." % err.args[0])
