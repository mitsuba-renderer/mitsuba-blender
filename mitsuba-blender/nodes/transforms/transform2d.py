import bpy
from bpy.props import FloatProperty
from ..base import MitsubaNode
from ...utils import math as math_utils

import math

class MitsubaNode2DTransform(bpy.types.Node, MitsubaNode):
    '''
    Shader node representing a Mitsuba 2d transform
    '''
    bl_idname = 'MitsubaNode2DTransform'
    bl_label = 'Transform 2D'
    bl_width_default = 190

    translate_x: FloatProperty(name='Translation X', default=0)
    translate_y: FloatProperty(name='Translation Y', default=0)

    rotate: FloatProperty(name='Rotation', default=0, min=(-math.pi * 2), max=(math.pi * 2),
                        subtype='ANGLE', unit='ROTATION')

    scale_x: FloatProperty(name='Scale X', default=1)
    scale_y: FloatProperty(name='Scale Y', default=1)

    def init(self, context):
        super().init(context)
        self.outputs.new('MitsubaSocket2DTransform', 'Transform')

    def draw_buttons(self, context, layout):
        layout.label(text='Translate')
        row = layout.row(align=True)
        row.prop(self, 'translate_x', text='X')
        row.prop(self, 'translate_y', text='Y')

        layout.label(text='Rotation')
        layout.prop(self, 'rotate', text='')

        layout.label(text='Scale')
        row = layout.row(align=True)
        row.prop(self, 'scale_x', text='X')
        row.prop(self, 'scale_y', text='Y')

    def to_dict(self, export_context):
        translation = [self.translate_x, self.translate_y]
        rotation = self.rotate
        scale = [self.scale_x, self.scale_y]
        return math_utils.compose_transform_2d(translation, rotation, scale)
