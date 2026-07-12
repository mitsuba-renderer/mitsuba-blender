'''Converters for Mitsuba's basic BSDF plugins.'''

from . import material_converter


@material_converter('diffuse')
def convert_diffuse(builder, mi_props):
    node = builder.node('ShaderNodeBsdfDiffuse')
    builder.set_color(node.inputs['Color'], mi_props, 'reflectance',
                      default=(0.8, 0.8, 0.8))
    return node.outputs['BSDF']
