import bpy
from bpy.utils import register_class, unregister_class
from bpy.props import FloatProperty, FloatVectorProperty

from .base import MitsubaSocket

class MitsubaSocketColors:
    '''
    Collection of default socket colors for various socket types
    '''
    bsdf = (0.39, 0.78, 0.39, 1.0)
    color_texture = (0.78, 0.78, 0.16, 1.0)
    float_texture = (0.63, 0.63, 0.63, 1.0)
    transform_2d = (0.65, 0.55, 0.75, 1.0)

class MitsubaSocketBSDF(bpy.types.NodeSocket, MitsubaSocket):
    color = MitsubaSocketColors.bsdf

class MitsubaSocketColorTexture(bpy.types.NodeSocket, MitsubaSocket):
    color = MitsubaSocketColors.color_texture
    default_value: FloatVectorProperty(subtype='COLOR', soft_min=0, soft_max=1, precision=3)

    def draw_prop(self, context, layout, node, text):
        split = layout.split(factor=0.7)
        split.label(text=text)
        split.prop(self, 'default_value', text='')

    def to_default_dict(self, export_context):
        return {
            'type': 'rgb',
            'value': list(self.default_value),
        }

class MitsubaSocketNormalMap(bpy.types.NodeSocket, MitsubaSocket):
    color = MitsubaSocketColors.color_texture

class MitsubaSocketFloatTexture(bpy.types.NodeSocket, MitsubaSocket):
    color = MitsubaSocketColors.float_texture

    def to_default_dict(self, export_context):
        return self.default_value

class MitsubaSocketFloatTextureNoDefault(MitsubaSocketFloatTexture):
    pass

class MitsubaSocketFloatTextureBounded0to1(MitsubaSocketFloatTexture):
    default_value: FloatProperty(min=0, max=1, description='Float value between 0 and 1')
    slider = True

class MitsubaSocketFloatTextureUnbounded(MitsubaSocketFloatTexture):
    default_value: FloatProperty(description='Float value')

class MitsubaSocket2DTransform(bpy.types.NodeSocket, MitsubaSocket):
    color = MitsubaSocketColors.transform_2d

###############################
##  Valid input connections  ##
###############################

MitsubaSocketBSDF.valid_inputs = { MitsubaSocketBSDF }

MitsubaSocketColorTexture.valid_inputs = { MitsubaSocketColorTexture }

MitsubaSocketNormalMap.valid_inputs = { MitsubaSocketColorTexture }

MitsubaSocketFloatTexture.valid_inputs = { MitsubaSocketFloatTexture, MitsubaSocketColorTexture }

MitsubaSocket2DTransform.valid_inputs = { MitsubaSocket2DTransform }

####################
##  Registration  ##
####################

classes = (
    MitsubaSocketBSDF,
    # MitsubaSocketColorTexture,
    # MitsubaSocketNormalMap,
    # MitsubaSocketFloatTextureNoDefault,
    # MitsubaSocketFloatTextureUnbounded,
    # MitsubaSocketFloatTextureBounded0to1,
    # MitsubaSocket2DTransform,
)

def register():
    for cls in classes:
        register_class(cls)

def unregister():
    for cls in classes:
        unregister_class(cls)
