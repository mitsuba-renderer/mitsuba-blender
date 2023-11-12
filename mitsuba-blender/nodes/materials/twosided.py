import bpy
from ..base import MitsubaNode

class MitsubaNodeTwosidedBSDF(bpy.types.Node, MitsubaNode):
    '''
    Shader node representing a Mitsuba twosided material
    '''
    bl_idname = 'MitsubaNodeTwosidedBSDF'
    bl_label = 'Twosided BSDF'

    def init(self, context):
        super().init(context)
        self.add_input('MitsubaSocketBSDF', 'BSDF')
        self.add_input('MitsubaSocketBSDF', 'BSDF', identifier='BSDF_001')

        self.outputs.new('MitsubaSocketBSDF', 'BSDF')

    def to_dict(self, export_context):
        params = { 'type': 'twosided' }
        bsdf1 = self.inputs[0].to_dict(export_context)
        bsdf2 = self.inputs[1].to_dict(export_context)
        if bsdf1 is None and bsdf2 is None:
            export_context.log('Twosided node must be connected to at least one BSDF', 'ERROR')
            return None
        if bsdf1 is not None:
            params['bsdf1'] = bsdf1
        if bsdf2 is not None:
            params['bsdf2'] = bsdf2
        return params
