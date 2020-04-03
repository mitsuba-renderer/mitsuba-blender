from numpy import pi
from mathutils import Matrix

RoughnessMode = {'GGX': 'ggx', 'SHARP': 'beckmann', 'BECKMANN': 'beckmann', 'ASHIKHMIN_SHIRLEY':'beckmann', 'MULTI_GGX':'ggx'}
#TODO: update when other distributions are supported

def convert_float_texture_node(export_ctx, socket):
    params = None

    if socket.is_linked:
        node = socket.links[0].from_node

        if node.type == "TEX_IMAGE":
            params = {
                'plugin': 'texture',
                'type': 'bitmap',
            }
            params['filename'] = node.image.filepath_from_user()#absolute path to texture
            #TODO: copy the image in the mitsuba scene folder
        else:
            raise NotImplementedError( "Node type %s is not supported. Only texture nodes are supported for float inputs" % node.type)

    else:
        params = socket.default_value

    return params

def convert_color_texture_node(export_ctx, socket):
    params = None

    if socket.is_linked:
        node = socket.links[0].from_node

        if node.type == "TEX_IMAGE":
            params = {
                'plugin': 'texture',
                'type': 'bitmap',
            }
            params['filename'] = node.image.filepath_from_user()#absolute path to texture
            #TODO: copy the image in the mitsuba scene folder

        elif node.type == "RGB": 
            #input rgb node
            params = export_ctx.spectrum(node.color, 'rgb')
        
        else:
            raise NotImplementedError("Node type %s is not supported. Only texture & RGB nodes are supported for color inputs" % node.type)

    else:
        params = export_ctx.spectrum(socket.default_value)

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

    return params

def convert_glossy_materials_cycles(export_ctx, current_node):
    params = {'plugin':'bsdf'}

    roughness = convert_float_texture_node(export_ctx, current_node.inputs['Roughness'])

    if roughness:
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

    return params

def convert_glass_materials_cycles(export_ctx, current_node):
    params = {'plugin': 'bsdf'}

    if current_node.inputs['IOR'].is_linked:
        raise NotImplementedError("Only default IOR value is supported in Mitsuba 2.")

    ior = current_node.inputs['IOR'].default_value
    
    roughness = convert_float_texture_node(export_ctx, current_node.inputs['Roughness'])

    if roughness:
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

    #we want the emitter object to be "shadeless", so we need to add it a dummy, empty bsdf, because all objects have a bsdf by default in mitsuba 2
    if 'empty-emitter-bsdf' not in export_ctx.scene_data:#we only need to add one of this, but we may have multiple emitter materials
        empty_bsdf = {
            'plugin':'bsdf',
            'type':'diffuse',
            'reflectance':export_ctx.spectrum(0),#no interaction with light
            'id':'empty-emitter-bsdf'
        }
        export_ctx.data_add(empty_bsdf)
    return params

def convert_mix_materials_cycles(export_ctx, current_node):#TODO: test and fix this
    add_shader = (current_node.type == 'ADD_SHADER')

    # in the case of AddShader 1-True = 0
    mat_I = current_node.inputs[1 - add_shader].links[0].from_node
    mat_II = current_node.inputs[2 - add_shader].links[0].from_node

    #TODO: XOR would be better in case of two emission type material
    emitter = ((mat_I.type == 'EMISSION') or (mat_II.type == 'EMISSION'))

    if emitter:
        params = cycles_material_to_dict(export_ctx, mat_I)
        params.update(cycles_material_to_dict(export_ctx, mat_II))

        return params

    else:
        if add_shader:
            weight = 0.5

        else:
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

#TODO: Add more support for other materials: refraction, transparent, translucent, principled
cycles_converters = {
    "BSDF_DIFFUSE": convert_diffuse_materials_cycles,
    'BSDF_GLOSSY': convert_glossy_materials_cycles,
    'BSDF_GLASS': convert_glass_materials_cycles,
    'EMISSION': convert_emitter_materials_cycles,
    'MIX_SHADER': convert_mix_materials_cycles,
    'ADD_SHADER': convert_mix_materials_cycles,
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
    mat_params['id'] = name
    export_ctx.data_add(mat_params)
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
