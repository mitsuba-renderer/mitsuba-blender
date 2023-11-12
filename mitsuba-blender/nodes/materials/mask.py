import bpy
from ..base import MitsubaNode

class MitsubaNodeMaskBSDF(bpy.types.Node, MitsubaNode):
    '''
    Shader node representing a Mitsuba mask material
    '''
    bl_idname = 'MitsubaNodeMaskBSDF'
    bl_label = 'Opacity Mask BSDF'

    def init(self, context):
        super().init(context)
        self.add_input('MitsubaSocketFloatTextureBounded0to1', 'Opacity', default=0.5)
        self.add_input('MitsubaSocketBSDF', 'BSDF')

        self.outputs.new('MitsubaSocketBSDF', 'BSDF')

    def to_dict(self, export_context):
        params = { 'type': 'mask' }
        
        bsdf = self.inputs['BSDF'].to_dict(export_context)
        if bsdf is None:
            export_context.log('Mask node does not have an input BSDF', 'ERROR')
            return None
        params['bsdf'] = bsdf
        params['opacity'] = self.inputs['Opacity'].to_dict(export_context)
        return params
