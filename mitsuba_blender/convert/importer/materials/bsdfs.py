'''Converters for Mitsuba's basic BSDF plugins.'''

import math

from . import material_converter, _rgba


@material_converter('diffuse')
def convert_diffuse(builder, mi_props):
    node = builder.node('ShaderNodeBsdfDiffuse')
    builder.set_color(node.inputs['Color'], mi_props, 'reflectance',
                      default=(0.8, 0.8, 0.8))
    return node.outputs['BSDF']


#################
##  Utilities  ##
#################

_IOR_VALUES = {
    'acetone': 1.36,
    'acrylic glass': 1.49,
    'air': 1.00028,
    'amber': 1.55,
    'benzene': 1.501,
    'bk7': 1.5046,
    'bromine': 1.661,
    'carbon dioxide': 1.00045,
    'carbon tetrachloride': 1.461,
    'diamond': 2.419,
    'ethanol': 1.361,
    'fused quartz': 1.458,
    'glycerol': 1.4729,
    'helium': 1.00004,
    'hydrogen': 1.00013,
    'pet': 1.575,
    'polypropylene': 1.49,
    'pyrex': 1.470,
    'silicone oil': 1.52045,
    'sodium chloride': 1.544,
    'vacuum': 1.0,
    'water': 1.3330,
    'water ice': 1.31,
}

def _ior(builder, mi_props, name, default):
    '''Read an IOR property, which is either a float or a material name.'''
    from mitsuba import Properties
    if name not in mi_props:
        return default
    if mi_props.type(name) == Properties.Type.String:
        value = mi_props[name]
        if value not in _IOR_VALUES:
            builder.mi_context.log(f'Unknown IOR material "{value}"; using '
                                   'the default value.', 'WARN')
            return default
        return _IOR_VALUES[value]
    return float(mi_props[name])


_DISTRIBUTIONS = {
    'beckmann': 'BECKMANN',
    'ggx': 'GGX',
}


def _set_distribution(builder, node, mi_props):
    name = mi_props.get('distribution', 'beckmann')
    if name not in _DISTRIBUTIONS:
        builder.mi_context.log(f'Microfacet distribution "{name}" is not '
                               'supported; using Beckmann.', 'WARN')
        name = 'beckmann'
    node.distribution = _DISTRIBUTIONS[name]


def _retro_reflectance(builder, mi_props, default=(1.0, 1.0, 1.0)):
    '''Estimate the reflection color of a BSDF by evaluating it head-on.
    Smooth conductors are delta lobes that evaluate to zero, so they are
    evaluated through an equivalent rough one.'''
    from mitsuba import (BSDFContext, Properties, SurfaceInteraction3f,
                         Vector3f, load_dict)
    try:
        bsdf_dict = {'type': mi_props.plugin_name()}
        for name in mi_props.keys():
            value = mi_props.get(name)
            # References index into the parser state; following them from
            # a standalone load_dict call would crash Mitsuba
            if isinstance(value, Properties.ResolvedReference):
                continue
            bsdf_dict[name] = value
        if bsdf_dict['type'] == 'conductor':
            bsdf_dict['type'] = 'roughconductor'
            bsdf_dict['alpha'] = 0.1
        bsdf = load_dict(bsdf_dict)
        si = SurfaceInteraction3f()
        si.wi = Vector3f(0.0, 0.0, 1.0)
        color, pdf = bsdf.eval_pdf(BSDFContext(), si,
                                   Vector3f(0.0, 0.0, 1.0))
        if pdf == 0.0:
            return list(default)
        return [min(float(c), 1.0) for c in color / pdf]
    except Exception as e:
        builder.mi_context.log('Could not evaluate the reflectance of '
                               f'"{mi_props.id() or mi_props.plugin_name()}"'
                               f': {e}. Using the default value.', 'WARN')
        return list(default)


def _set_anisotropy(builder, node, mi_props):
    '''Convert alpha_u/alpha_v back into Cycles' roughness/anisotropy pair
    (the inverse of the mapping in the exporter).'''
    from mitsuba import Properties

    def constant(name):
        if name in mi_props and \
                mi_props.type(name) == Properties.Type.Float:
            return float(mi_props[name])
        return None

    alpha_u = constant('alpha_u')
    alpha_v = constant('alpha_v')
    if alpha_u is None or alpha_v is None:
        builder.mi_context.log('Only constant alpha_u/alpha_v values are '
                               'supported; ignoring the anisotropy.', 'WARN')
        node.inputs['Roughness'].default_value = math.sqrt(0.1)
        return
    sign = 1.0
    if alpha_u < alpha_v:
        alpha_u, alpha_v = alpha_v, alpha_u
        sign = -1.0
    aspect_sqr = alpha_v / alpha_u if alpha_u > 0.0 else 1.0
    node.inputs['Roughness'].default_value = (alpha_u * alpha_v) ** 0.25
    node.inputs['Anisotropy'].default_value = sign * (1.0 - aspect_sqr) / 0.9


##################
##  Conductors  ##
##################

@material_converter('conductor')
def convert_conductor(builder, mi_props):
    node = builder.node('ShaderNodeBsdfAnisotropic')
    node.inputs['Roughness'].default_value = 0.0
    node.inputs['Color'].default_value = \
        _rgba(_retro_reflectance(builder, mi_props))
    return node.outputs['BSDF']


@material_converter('roughconductor')
def convert_roughconductor(builder, mi_props):
    node = builder.node('ShaderNodeBsdfAnisotropic')
    _set_distribution(builder, node, mi_props)
    node.inputs['Color'].default_value = \
        _rgba(_retro_reflectance(builder, mi_props))
    if 'alpha_u' in mi_props or 'alpha_v' in mi_props:
        _set_anisotropy(builder, node, mi_props)
    else:
        builder.set_float(node.inputs['Roughness'], mi_props, 'alpha',
                          default=0.1, transform=math.sqrt)
    return node.outputs['BSDF']


###################
##  Dielectrics  ##
###################

@material_converter('dielectric')
def convert_dielectric(builder, mi_props):
    node = builder.node('ShaderNodeBsdfGlass')
    node.inputs['Roughness'].default_value = 0.0
    node.inputs['IOR'].default_value = _ior(builder, mi_props, 'int_ior',
                                            1.5046)
    builder.set_color(node.inputs['Color'], mi_props,
                      'specular_transmittance', default=(1.0, 1.0, 1.0))
    return node.outputs['BSDF']


@material_converter('thindielectric')
def convert_thindielectric(builder, mi_props):
    node = builder.node('ShaderNodeBsdfGlass')
    node.inputs['Roughness'].default_value = 0.0
    node.inputs['IOR'].default_value = 1.0
    builder.set_color(node.inputs['Color'], mi_props,
                      'specular_transmittance', default=(1.0, 1.0, 1.0))
    return node.outputs['BSDF']


@material_converter('roughdielectric')
def convert_roughdielectric(builder, mi_props):
    node = builder.node('ShaderNodeBsdfGlass')
    _set_distribution(builder, node, mi_props)
    node.inputs['IOR'].default_value = _ior(builder, mi_props, 'int_ior',
                                            1.5046)
    builder.set_color(node.inputs['Color'], mi_props,
                      'specular_transmittance', default=(1.0, 1.0, 1.0))
    builder.set_float(node.inputs['Roughness'], mi_props, 'alpha',
                      default=0.1, transform=math.sqrt)
    return node.outputs['BSDF']


################
##  Plastics  ##
################

@material_converter('plastic', 'roughplastic')
def convert_plastic(builder, mi_props):
    # Blender has no plastic BSDF; a Principled node with the plastic's
    # diffuse base, IOR and roughness is a close approximation (the diffuse
    # and specular lobes are not energy-coupled like in Mitsuba)
    plugin_name = mi_props.plugin_name()
    builder.mi_context.log(f'Approximating Mitsuba "{plugin_name}" with a '
                           'Principled BSDF.', 'WARN')
    node = builder.node('ShaderNodeBsdfPrincipled')
    builder.set_color(node.inputs['Base Color'], mi_props,
                      'diffuse_reflectance', default=(0.5, 0.5, 0.5))
    node.inputs['IOR'].default_value = _ior(builder, mi_props, 'int_ior',
                                            1.49)
    if plugin_name == 'roughplastic':
        builder.set_float(node.inputs['Roughness'], mi_props, 'alpha',
                          default=0.1, transform=math.sqrt)
    else:
        node.inputs['Roughness'].default_value = 0.0
    return node.outputs['BSDF']
