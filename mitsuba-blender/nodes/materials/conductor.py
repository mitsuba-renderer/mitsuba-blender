import bpy
from ..base import MitsubaNode
from .utils import ConductorPropertyHelper, AnisotropicRoughnessPropertyHelper

class MitsubaNodeConductorBSDF(bpy.types.Node, MitsubaNode, ConductorPropertyHelper):
    '''
    Shader node representing a Mitsuba conductor material
    '''
    bl_idname = 'MitsubaNodeConductorBSDF'
    bl_label = 'Conductor BSDF'
    bl_width_default = 190

    def init(self, context):
        super().init(context)
        self.add_conductor_inputs()
        self.add_input('MitsubaSocketColorTexture', 'Specular Reflectance', default=(1.0, 1.0, 1.0))

        self.outputs.new('MitsubaSocketBSDF', 'BSDF')

        self.conductor_enum = 'none'

    def draw_buttons(self, context, layout):
        self.draw_conductor_props(context, layout)

    def to_dict(self, export_context):
        params = { 'type': 'conductor' }
        self.write_conductor_props_to_dict(params, export_context)
        params['specular_reflectance'] = self.inputs['Specular Reflectance'].to_dict(export_context)
        return params

class MitsubaNodeRoughConductorBSDF(bpy.types.Node, MitsubaNode, ConductorPropertyHelper, AnisotropicRoughnessPropertyHelper):
    '''
    Shader node representing a Mitsuba conductor material
    '''
    bl_idname = 'MitsubaNodeRoughConductorBSDF'
    bl_label = 'Rough Conductor BSDF'
    bl_width_default = 190

    def init(self, context):
        super().init(context)
        self.add_conductor_inputs()
        self.add_roughness_inputs()
        self.add_input('MitsubaSocketColorTexture', 'Specular Reflectance', default=(1.0, 1.0, 1.0))

        self.outputs.new('MitsubaSocketBSDF', 'BSDF')

        self.conductor_enum = 'none'

    def draw_buttons(self, context, layout):
        self.draw_roughness_props(context, layout)
        self.draw_conductor_props(context, layout)

    def to_dict(self, export_context):
        params = { 'type': 'roughconductor' }
        self.write_conductor_props_to_dict(params, export_context)
        self.write_roughness_props_to_dict(params, export_context)
        params['specular_reflectance'] = self.inputs['Specular Reflectance'].to_dict(export_context)
        return params
