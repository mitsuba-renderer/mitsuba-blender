import bpy
from ..base import MitsubaNode
from .utils import TwosidedIORPropertyHelper, AnisotropicRoughnessPropertyHelper

class MitsubaNodeDielectricBSDF(bpy.types.Node, MitsubaNode, TwosidedIORPropertyHelper):
    '''
    Shader node representing a Mitsuba dielectric material
    '''
    bl_idname = 'MitsubaNodeDielectricBSDF'
    bl_label = 'Dielectric BSDF'
    bl_width_default = 190

    def init(self, context):
        super().init(context)
        self.add_input('MitsubaSocketColorTexture', 'Specular Reflectance', default=(1.0, 1.0, 1.0))
        self.add_input('MitsubaSocketColorTexture', 'Specular Transmittance', default=(1.0, 1.0, 1.0))

        self.outputs.new('MitsubaSocketBSDF', 'BSDF')

        self.int_ior_enum = 'bk7'
        self.ext_ior_enum = 'bk7'

    def draw_buttons(self, context, layout):
        self.draw_ior_props(context, layout)

    def to_dict(self, export_context):
        params = { 'type': 'dielectric' }
        self.write_ior_props_to_dict(params, export_context)
        params['specular_reflectance'] = self.inputs['Specular Reflectance'].to_dict(export_context)
        params['specular_transmittance'] = self.inputs['Specular Transmittance'].to_dict(export_context)
        return params

class MitsubaNodeThinDielectricBSDF(bpy.types.Node, MitsubaNode, TwosidedIORPropertyHelper):
    '''
    Shader node representing a Mitsuba thin dielectric material
    '''
    bl_idname = 'MitsubaNodeThinDielectricBSDF'
    bl_label = 'Thin Dielectric BSDF'
    bl_width_default = 190

    def init(self, context):
        super().init(context)
        self.add_input('MitsubaSocketColorTexture', 'Specular Reflectance', default=(1.0, 1.0, 1.0))
        self.add_input('MitsubaSocketColorTexture', 'Specular Transmittance', default=(1.0, 1.0, 1.0))

        self.outputs.new('MitsubaSocketBSDF', 'BSDF')

        self.int_ior_enum = 'bk7'
        self.ext_ior_enum = 'bk7'

    def draw_buttons(self, context, layout):
        self.draw_ior_props(context, layout)

    def to_dict(self, export_context):
        params = { 'type': 'thindielectric' }
        self.write_ior_props_to_dict(params, export_context)
        params['specular_reflectance'] = self.inputs['Specular Reflectance'].to_dict(export_context)
        params['specular_transmittance'] = self.inputs['Specular Transmittance'].to_dict(export_context)
        return params

class MitsubaNodeRoughDielectricBSDF(bpy.types.Node, MitsubaNode, TwosidedIORPropertyHelper, AnisotropicRoughnessPropertyHelper):
    '''
    Shader node representing a Mitsuba thin dielectric material
    '''
    bl_idname = 'MitsubaNodeRoughDielectricBSDF'
    bl_label = 'Rough Dielectric BSDF'
    bl_width_default = 190

    def init(self, context):
        super().init(context)
        self.add_input('MitsubaSocketColorTexture', 'Specular Reflectance', default=(1.0, 1.0, 1.0))
        self.add_input('MitsubaSocketColorTexture', 'Specular Transmittance', default=(1.0, 1.0, 1.0))
        self.add_roughness_inputs()

        self.outputs.new('MitsubaSocketBSDF', 'BSDF')

        self.int_ior_enum = 'bk7'
        self.ext_ior_enum = 'bk7'

    def draw_buttons(self, context, layout):
        self.draw_roughness_props(context, layout)
        self.draw_ior_props(context, layout)

    def to_dict(self, export_context):
        params = { 'type': 'roughdielectric' }
        self.write_ior_props_to_dict(params, export_context)
        self.write_roughness_props_to_dict(params, export_context)
        params['specular_reflectance'] = self.inputs['Specular Reflectance'].to_dict(export_context)
        params['specular_transmittance'] = self.inputs['Specular Transmittance'].to_dict(export_context)
        return params
