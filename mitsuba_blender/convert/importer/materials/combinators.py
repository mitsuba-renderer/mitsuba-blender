'''Converters for Mitsuba's BSDF combinator plugins: twosided, blendbsdf,
mask and null.'''

from ... import ConversionError
from . import material_converter


def _child_bsdfs(builder, mi_props):
    '''The Mitsuba properties of the BSDFs nested in this one, in order.'''
    from mitsuba import ObjectType, Properties
    children = []
    for _, value in mi_props.items():
        if isinstance(value, Properties.ResolvedReference):
            node = builder.mi_context.mi_state.nodes[value.index()]
            if node.type == ObjectType.BSDF:
                children.append(node.props)
    return children


@material_converter('twosided')
def convert_twosided(builder, mi_props):
    children = _child_bsdfs(builder, mi_props)
    if len(children) == 1:
        # Blender materials are two-sided by default
        return builder.convert_bsdf(children[0])
    if len(children) == 2:
        # Select between the front and back BSDF by face orientation
        mix = builder.node('ShaderNodeMixShader')
        geometry = builder.node('ShaderNodeNewGeometry')
        builder.link(geometry.outputs['Backfacing'], mix.inputs['Fac'])
        builder.link(builder.convert_bsdf(children[0]), mix.inputs[1])
        builder.link(builder.convert_bsdf(children[1]), mix.inputs[2])
        return mix.outputs['Shader']
    raise ConversionError(f'twosided BSDF has {len(children)} nested '
                          'BSDFs, expected 1 or 2')


@material_converter('blendbsdf')
def convert_blendbsdf(builder, mi_props):
    children = _child_bsdfs(builder, mi_props)
    if len(children) != 2:
        raise ConversionError(f'blendbsdf has {len(children)} nested '
                              'BSDFs, expected 2')
    # A weight of zero selects the first BSDF, matching the Fac semantics
    mix = builder.node('ShaderNodeMixShader')
    builder.set_float(mix.inputs['Fac'], mi_props, 'weight', default=0.5)
    builder.link(builder.convert_bsdf(children[0]), mix.inputs[1])
    builder.link(builder.convert_bsdf(children[1]), mix.inputs[2])
    return mix.outputs['Shader']


def _constant_opacity(mi_props):
    '''The opacity as an RGB list when it is a constant, else None.'''
    from mitsuba import Properties
    if 'opacity' not in mi_props:
        return [0.5, 0.5, 0.5]
    prop_type = mi_props.type('opacity')
    if prop_type == Properties.Type.Color:
        return list(mi_props['opacity'])
    if prop_type == Properties.Type.Float:
        return [mi_props['opacity']] * 3
    return None


def _is_black_diffuse(mi_props):
    from mitsuba import Properties
    return (mi_props.plugin_name() == 'diffuse'
            and 'reflectance' in mi_props
            and mi_props.type('reflectance') == Properties.Type.Color
            and max(list(mi_props['reflectance'])) == 0)


@material_converter('mask')
def convert_mask(builder, mi_props):
    children = _child_bsdfs(builder, mi_props)
    if len(children) != 1:
        raise ConversionError(f'mask BSDF has {len(children)} nested '
                              'BSDFs, expected 1')
    opacity = _constant_opacity(mi_props)
    if opacity is not None and _is_black_diffuse(children[0]):
        # A masked black diffuse is plain transparency; Blender's
        # Transparent BSDF color is the inverse of Mitsuba's opacity
        node = builder.node('ShaderNodeBsdfTransparent')
        node.inputs['Color'].default_value = \
            [1.0 - c for c in opacity] + [1.0]
        return node.outputs['BSDF']
    mix = builder.node('ShaderNodeMixShader')
    builder.set_float(mix.inputs['Fac'], mi_props, 'opacity', default=0.5)
    transparent = builder.node('ShaderNodeBsdfTransparent')
    builder.link(transparent.outputs['BSDF'], mix.inputs[1])
    builder.link(builder.convert_bsdf(children[0]), mix.inputs[2])
    return mix.outputs['Shader']


@material_converter('null')
def convert_null(builder, mi_props):
    return builder.node('ShaderNodeBsdfTransparent').outputs['BSDF']
