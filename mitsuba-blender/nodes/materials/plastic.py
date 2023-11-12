import bpy
from bpy.props import BoolProperty
from ..base import MitsubaNode
from .utils import TwosidedIORPropertyHelper, RoughnessPropertyHelper

class MitsubaNodePlasticBSDF(bpy.types.Node, MitsubaNode, TwosidedIORPropertyHelper):
    '''
    Shader node representing a Mitsuba plastic material
    '''
    bl_idname = 'MitsubaNodePlasticBSDF'
    bl_label = 'Plastic BSDF'
    bl_width_default = 190

    nonlinear: BoolProperty(name='Nonlinear', default=False)

    def init(self, context):
        super().init(context)
        self.add_input('MitsubaSocketColorTexture', 'Diffuse Reflectance', default=(0.5, 0.5, 0.5))
        self.add_input('MitsubaSocketColorTexture', 'Specular Reflectance', default=(1.0, 1.0, 1.0))

        self.outputs.new('MitsubaSocketBSDF', 'BSDF')

        self.int_ior_enum = 'polypropylene'
        self.ext_ior_enum = 'air'

    def draw_buttons(self, context, layout):
        layout.prop(self, 'nonlinear')
        self.draw_ior_props(context, layout)

    def to_dict(self, export_context):
        params = { 'type': 'plastic' }
        params['diffuse_reflectance'] = self.inputs['Diffuse Reflectance'].to_dict(export_context)
        params['nonlinear'] = self.nonlinear
        self.write_ior_props_to_dict(params, export_context)
        params['specular_reflectance'] = self.inputs['Specular Reflectance'].to_dict(export_context)
        return params

class MitsubaNodeRoughPlasticBSDF(bpy.types.Node, MitsubaNode, TwosidedIORPropertyHelper, RoughnessPropertyHelper):
    '''
    Shader node representing a Mitsuba rough plastic material
    '''
    bl_idname = 'MitsubaNodeRoughPlasticBSDF'
    bl_label = 'Rough Plastic BSDF'
    bl_width_default = 190

    nonlinear: BoolProperty(name='Nonlinear', default=False)

    def init(self, context):
        super().init(context)
        self.add_input('MitsubaSocketColorTexture', 'Diffuse Reflectance', default=(0.5, 0.5, 0.5))
        self.add_input('MitsubaSocketColorTexture', 'Specular Reflectance', default=(1.0, 1.0, 1.0))
        self.add_roughness_inputs()

        self.outputs.new('MitsubaSocketBSDF', 'BSDF')

        self.int_ior_enum = 'polypropylene'
        self.ext_ior_enum = 'air'

    def draw_buttons(self, context, layout):
        self.draw_roughness_props(context, layout)
        layout.prop(self, 'nonlinear')
        self.draw_ior_props(context, layout)

    def to_dict(self, export_context):
        params = { 'type': 'roughplastic' }
        params['diffuse_reflectance'] = self.inputs['Diffuse Reflectance'].to_dict(export_context)
        params['nonlinear'] = self.nonlinear
        self.write_ior_props_to_dict(params, export_context)
        self.write_roughness_props_to_dict(params, export_context)
        params['specular_reflectance'] = self.inputs['Specular Reflectance'].to_dict(export_context)
        return params
