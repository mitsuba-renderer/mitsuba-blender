import bpy
from nodeitems_utils import NodeCategory, NodeItem

from ..base import MitsubaNodeTree

class MitsubaNodeTreeMaterial(bpy.types.NodeTree, MitsubaNodeTree):
    '''
    Custom Blender Node Tree for Mitsuba BSDFs
    '''
    bl_idname = 'mitsuba_material_nodes'
    bl_label = 'Mitsuba Material Editor'
    bl_icon = 'NODE_MATERIAL'

    @classmethod
    def get_from_context(cls, context):
        '''
        Updates the node tree with the currently selected material
        '''
        obj = context.active_object
        if obj and obj.type not in { 'LIGHT', 'CAMERA' }:
            mat = obj.active_material
            if mat:
                node_tree = mat.mitsuba.node_tree
                if node_tree:
                    return node_tree, mat, mat
        return None, None, None

class MitsubaNodeCategoryMaterial(NodeCategory):
    @classmethod
    def poll(cls, context):
        return context.space_data.tree_type == MitsubaNodeTreeMaterial.bl_idname

mitsuba_node_categories_material = [
    MitsubaNodeCategoryMaterial('MITSUBA_MATERIAL_BSDF', 'BSDFs', items=[
    #     NodeItem('MitsubaNodeTwosidedBSDF', label='Twosided'),
    #     NodeItem('MitsubaNodeDiffuseBSDF', label='Diffuse'),
    #     NodeItem('MitsubaNodeDielectricBSDF', label='Dielectric'),
    #     NodeItem('MitsubaNodeThinDielectricBSDF', label='Thin Dielectric'),
    #     NodeItem('MitsubaNodeRoughDielectricBSDF', label='Rough Dielectric'),
    #     NodeItem('MitsubaNodeConductorBSDF', label='Conductor'),
    #     NodeItem('MitsubaNodeRoughConductorBSDF', label='Rough Conductor'),
    #     NodeItem('MitsubaNodePlasticBSDF', label='Plastic'),
    #     NodeItem('MitsubaNodeRoughPlasticBSDF', label='Rough Plastic'),
    #     NodeItem('MitsubaNodeBumpMapBSDF', label='Bump Map'),
    #     NodeItem('MitsubaNodeNormalMapBSDF', label='Normal Map'),
    #     NodeItem('MitsubaNodeBlendBSDF', label='Blend'),
    #     NodeItem('MitsubaNodeMaskBSDF', label='Opacity Mask'),
        NodeItem('MitsubaNodeNullBSDF', label='Null'),
    #     NodeItem('MitsubaNodePrincipledBSDF', label='Principled'),
    ]),

    # MitsubaNodeCategoryMaterial('MITSUBA_MATERIAL_TEXTURE', 'Textures', items=[
    #     NodeItem('MitsubaNodeBitmapTexture', label='Bitmap'),
    #     NodeItem('MitsubaNodeCheckerboardTexture', label='Checkerboard'),
    # ]),

    MitsubaNodeCategoryMaterial('MITSUBA_MATERIAL_OUTPUT', 'Output', items=[
        NodeItem('MitsubaNodeOutputMaterial', label='Output'),
    ]),

    # MitsubaNodeCategoryMaterial('MITSUBA_MATERIAL_TRANSFORM', 'Transforms', items=[
    #     NodeItem('MitsubaNode2DTransform', label='Transform 2D'),
    # ]),
]
