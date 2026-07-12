'''Converter for Mitsuba's principled BSDF.'''

from . import material_converter


def _set_spec_tint(builder, node, mi_props):
    '''Mitsuba's spec_tint blends the specular color from white toward the
    base color hue; Blender tints with a color where white means untinted.'''
    from mitsuba import Properties
    if 'spec_tint' not in mi_props:
        return
    prop_type = mi_props.type('spec_tint')
    if prop_type == Properties.Type.Float:
        tint = mi_props['spec_tint']
    elif prop_type == Properties.Type.Color:
        rgb = list(mi_props['spec_tint'])
        tint = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    else:
        builder.mi_context.log('Only constant spec_tint values are '
                               'supported; ignoring it.', 'WARN')
        return
    gray = 1.0 - tint
    node.inputs['Specular Tint'].default_value = (gray, gray, gray, 1.0)


def _set_ior(builder, node, mi_props):
    '''Fill the IOR and Specular IOR Level inputs from either of Mitsuba's
    mutually exclusive eta/specular parameters, keeping both sockets
    consistent (F0 = 0.08 * specular level).'''
    import math
    from mitsuba import Properties
    for name in ('eta', 'specular'):
        if name in mi_props and \
                mi_props.type(name) != Properties.Type.Float:
            builder.mi_context.log(f'Only constant {name} values are '
                                   'supported; ignoring it.', 'WARN')
            return
    if 'eta' in mi_props:
        eta = mi_props['eta']
        specular = ((eta - 1.0) / (eta + 1.0)) ** 2 / 0.08
    elif 'specular' in mi_props:
        specular = mi_props['specular']
        eta = 2.0 / (1.0 - math.sqrt(min(0.08 * specular, 0.9999))) - 1.0
    else:
        return
    node.inputs['IOR'].default_value = eta
    node.inputs['Specular IOR Level'].default_value = min(specular, 1.0)


@material_converter('principled')
def convert_principled(builder, mi_props):
    node = builder.node('ShaderNodeBsdfPrincipled')
    builder.set_color(node.inputs['Base Color'], mi_props, 'base_color',
                      default=(0.5, 0.5, 0.5))
    builder.set_float(node.inputs['Roughness'], mi_props, 'roughness',
                      default=0.5)
    builder.set_float(node.inputs['Metallic'], mi_props, 'metallic')
    builder.set_float(node.inputs['Anisotropic'], mi_props, 'anisotropic')
    builder.set_float(node.inputs['Transmission Weight'], mi_props,
                      'spec_trans')
    builder.set_float(node.inputs['Sheen Weight'], mi_props, 'sheen')
    builder.set_color(node.inputs['Sheen Tint'], mi_props, 'sheen_tint')
    builder.set_float(node.inputs['Coat Weight'], mi_props, 'clearcoat')
    # Coat Roughness is the inverse of Mitsuba's clearcoat gloss
    builder.set_float(node.inputs['Coat Roughness'], mi_props,
                      'clearcoat_gloss', transform=lambda gloss: 1.0 - gloss)
    _set_spec_tint(builder, node, mi_props)
    _set_ior(builder, node, mi_props)
    return node.outputs['BSDF']
