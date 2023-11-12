import bpy
from ..base import MitsubaNode

class MitsubaNodeBlendBSDF(bpy.types.Node, MitsubaNode):
    '''
    Shader node representing a Mitsuba blend material
    '''
    bl_idname = 'MitsubaNodeBlendBSDF'
    bl_label = 'Blend BSDF'

    def init(self, context):
        super().init(context)
        self.add_input('MitsubaSocketFloatTextureBounded0to1', 'Weight', default=0.5)
        self.add_input('MitsubaSocketBSDF', 'BSDF')
        self.add_input('MitsubaSocketBSDF', 'BSDF', identifier='BSDF_001')

        self.outputs.new('MitsubaSocketBSDF', 'BSDF')

    def to_dict(self, export_context):
        params = { 'type': 'blendbsdf' }
        params['weight'] = self.inputs['Weight'].to_dict(export_context)

        bsdf1 = self.inputs[1].to_dict(export_context)
        bsdf2 = self.inputs[2].to_dict(export_context)
        if bsdf1 is None or bsdf2 is None:
            export_context.log('Blend node does not have two input BSDFs', 'ERROR')
            return None
        params['bsdf1'] = bsdf1
        params['bsdf2'] = bsdf2
        return params
