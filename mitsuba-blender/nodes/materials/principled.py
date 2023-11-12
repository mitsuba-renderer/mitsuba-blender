import bpy
from bpy.props import FloatProperty
from .utils import OnesidedIORPropertyHelper
from ..base import MitsubaNode

class MitsubaNodePrincipledBSDF(bpy.types.Node, MitsubaNode, OnesidedIORPropertyHelper):
    '''
    Shader node representing a Mitsuba principled material
    '''
    bl_idname = 'MitsubaNodePrincipledBSDF'
    bl_label = 'Principled BSDF'
    bl_width_default = 190

    def init(self, context):
        super().init(context)
        self.add_input('MitsubaSocketColorTexture', 'Base Color', default=(0.5, 0.5, 0.5))
        self.add_input('MitsubaSocketFloatTextureBounded0to1', 'Roughness', default=0.5)
        self.add_input('MitsubaSocketFloatTextureBounded0to1', 'Anisotropic', default=0.0)
        self.add_input('MitsubaSocketFloatTextureBounded0to1', 'Metallic', default=0.0)
        self.add_input('MitsubaSocketFloatTextureBounded0to1', 'Specular Transmission', default=0.0)
        self.add_input('MitsubaSocketFloatTextureBounded0to1', 'Specular Tint', default=0.0)
        self.add_input('MitsubaSocketFloatTextureBounded0to1', 'Sheen', default=0.0)
        self.add_input('MitsubaSocketFloatTextureBounded0to1', 'Sheen Tint', default=0.0)
        self.add_input('MitsubaSocketFloatTextureBounded0to1', 'Flatness', default=0.0)
        self.add_input('MitsubaSocketFloatTextureBounded0to1', 'Clearcoat', default=0.0)
        self.add_input('MitsubaSocketFloatTextureBounded0to1', 'Clearcoat Gloss', default=0.0)

        self.outputs.new('MitsubaSocketBSDF', 'BSDF')

    def draw_buttons(self, context, layout):
        self.draw_ior_props(context, layout)

    def to_dict(self, export_context):
        params = { 'type': 'principled' }
        params['base_color'] = self.inputs['Base Color'].to_dict(export_context)
        params['roughness'] = self.inputs['Roughness'].to_dict(export_context)
        params['anisotropic'] = self.inputs['Anisotropic'].to_dict(export_context)
        params['metallic'] = self.inputs['Metallic'].to_dict(export_context)
        params['spec_trans'] = self.inputs['Specular Transmission'].to_dict(export_context)
        params['spec_tint'] = self.inputs['Specular Tint'].to_dict(export_context)
        params['sheen'] = self.inputs['Sheen'].to_dict(export_context)
        params['sheen_tint'] = self.inputs['Sheen Tint'].to_dict(export_context)
        params['flatness'] = self.inputs['Flatness'].to_dict(export_context)
        params['clearcoat'] = self.inputs['Clearcoat'].to_dict(export_context)
        params['clearcoat_gloss'] = self.inputs['Clearcoat Gloss'].to_dict(export_context)
        self.write_ior_props_to_dict(params, export_context)
        return params
