RoughnessMode = {
    'GGX': 'ggx',
    'BECKMANN': 'beckmann',
    'ASHIKHMIN_SHIRLEY': 'beckmann',
    'MULTI_GGX': 'ggx'
}

def cycles_material_to_dict(ctx, node, extra):
    '''
    Converting one material from Blender to Mitsuba dict
    '''
    from . import CONVERTERS
    if node.type in CONVERTERS:
        params = CONVERTERS[node.type](ctx, node, extra)
    else:
        raise NotImplementedError("Node type: %s is not supported in Mitsuba." % node.type)

    return params

def get_default_material(ctx):
    '''
    Create the default material
    '''
    return {
        'type': 'diffuse',
        'reflectance': ctx.spectrum([1.0, 0.0, 0.3]),
    }