import bpy
from ..base import MitsubaNode

class MitsubaNodeCheckerboardTexture(bpy.types.Node, MitsubaNode):
    '''
    Shader node representing a Mitsuba checkerboard texture
    '''
    bl_idname = 'MitsubaNodeCheckerboardTexture'
    bl_label = 'Checkerboard Texture'

    def init(self, context):
        super().init(context)
        self.add_input('MitsubaSocketColorTexture', 'Color 0', default=(0.4, 0.4, 0.4))
        self.add_input('MitsubaSocketColorTexture', 'Color 1', default=(0.2, 0.2, 0.2))
        self.add_input('MitsubaSocket2DTransform', 'Transform')

        self.outputs.new('MitsubaSocketColorTexture', 'Color')

    def to_dict(self, export_context):
        params = { 'type': 'checkerboard' }
        params['color0'] = self.inputs['Color 0'].to_dict(export_context)
        params['color1'] = self.inputs['Color 1'].to_dict(export_context)
        transform = self.inputs['Transform'].to_dict(export_context)
        if transform is not None:
            params['to_uv'] = transform
        return params
