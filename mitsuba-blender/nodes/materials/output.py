import bpy
from ..base import MitsubaNodeOutput

class MitsubaNodeOutputMaterial(bpy.types.Node, MitsubaNodeOutput):
    '''
    Shader node representing a Mitsuba material output
    '''
    bl_idname = 'MitsubaNodeOutputMaterial'
    bl_label = 'Material Output'

    def init(self, context):
        self.add_input('MitsubaSocketBSDF', 'BSDF')
        super().init(context)

    def draw_buttons(self, context, layout):
        super().draw_buttons(context, layout)

    def to_dict(self, export_context):
        if not self.is_active:
            export_context.log('Output node is not active. Skipping.', 'WARN')
            return None
        return self.inputs['BSDF'].to_dict(export_context)
