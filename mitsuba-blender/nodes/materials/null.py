import bpy
from ..base import MitsubaNode

class MitsubaNodeNullBSDF(bpy.types.Node, MitsubaNode):
    '''
    Shader node representing a Mitsuba null material
    '''
    bl_idname = 'MitsubaNodeNullBSDF'
    bl_label = 'Null BSDF'

    def init(self, context):
        super().init(context)
        self.outputs.new('MitsubaSocketBSDF', 'BSDF')

    def to_dict(self, export_context):
        params = { 'type': 'null' }
        return params
