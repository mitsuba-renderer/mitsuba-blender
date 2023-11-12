import bpy
from bpy.props import FloatProperty
from ..base import MitsubaNode

class MitsubaNodeBumpMapBSDF(bpy.types.Node, MitsubaNode):
    '''
    Shader node representing a Mitsuba bump material
    '''
    bl_idname = 'MitsubaNodeBumpMapBSDF'
    bl_label = 'Bump Map BSDF'

    scale: FloatProperty(name='Scale', default=1)

    def init(self, context):
        super().init(context)
        self.add_input('MitsubaSocketBSDF', 'BSDF')
        self.add_input('MitsubaSocketFloatTextureNoDefault', 'Bump Height')

        self.outputs.new('MitsubaSocketBSDF', 'BSDF')

    def draw_buttons(self, context, layout):
        layout.prop(self, 'scale')

    def to_dict(self, export_context):
        params = { 'type': 'bumpmap' }

        bsdf = self.inputs['BSDF'].to_dict(export_context)
        if bsdf is None:
            export_context.log('Bump map node does not have an input BSDF', 'ERROR')
            return None
        params['bsdf'] = bsdf

        bump = self.inputs['Bump Height'].to_dict(export_context)
        if bump is None:
            export_context.log('Bump map node does not have a bump texture', 'ERROR')
            return None
        params['bump'] = bump

        params['scale'] = self.scale
        return params
