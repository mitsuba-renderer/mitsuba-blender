import bpy
from ..base import MitsubaNode

class MitsubaNodeDiffuseBSDF(bpy.types.Node, MitsubaNode):
    '''
    Shader node representing a Mitsuba diffuse material
    '''
    bl_idname = 'MitsubaNodeDiffuseBSDF'
    bl_label = 'Diffuse BSDF'

    def init(self, context):
        super().init(context)
        self.add_input('MitsubaSocketColorTexture', 'Reflectance', default=(0.5, 0.5, 0.5))

        self.outputs.new('MitsubaSocketBSDF', 'BSDF')

    def to_dict(self, export_context):
        params = { 'type': 'diffuse' }
        params['reflectance'] = self.inputs['Reflectance'].to_dict(export_context)
        return params
