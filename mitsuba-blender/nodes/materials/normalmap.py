import bpy
from ..base import MitsubaNode

class MitsubaNodeNormalMapBSDF(bpy.types.Node, MitsubaNode):
    '''
    Shader node representing a Mitsuba normal map material
    '''
    bl_idname = 'MitsubaNodeNormalMapBSDF'
    bl_label = 'Normal Map BSDF'

    def init(self, context):
        super().init(context)
        self.add_input('MitsubaSocketBSDF', 'BSDF')
        self.add_input('MitsubaSocketNormalMap', 'Normal Map')

        self.outputs.new('MitsubaSocketBSDF', 'BSDF')

    def to_dict(self, export_context):
        params = { 'type': 'normalmap' }

        bsdf = self.inputs['BSDF'].to_dict(export_context)
        if bsdf is None:
            export_context.log('Normal map node does not have an input BSDF', 'ERROR')
            return None
        params['bsdf'] = bsdf
        params['normalmap'] = self.inputs['Normal Map'].to_dict(export_context)
        return params
