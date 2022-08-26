from bpy.utils import register_class, unregister_class
from nodeitems_utils import register_node_categories, unregister_node_categories

from . import (
    blend, bumpmap, nodetree, output, twosided, diffuse, dielectric, conductor, plastic, normalmap, mask, null, principled
)

from .nodetree import mitsuba_node_categories_material

classes = (
    nodetree.MitsubaNodeTreeMaterial,
    output.MitsubaNodeOutputMaterial,
    twosided.MitsubaNodeTwosidedBSDF,
    diffuse.MitsubaNodeDiffuseBSDF,
    dielectric.MitsubaNodeDielectricBSDF,
    dielectric.MitsubaNodeThinDielectricBSDF,
    dielectric.MitsubaNodeRoughDielectricBSDF,
    conductor.MitsubaNodeConductorBSDF,
    conductor.MitsubaNodeRoughConductorBSDF,
    plastic.MitsubaNodePlasticBSDF,
    plastic.MitsubaNodeRoughPlasticBSDF,
    bumpmap.MitsubaNodeBumpMapBSDF,
    normalmap.MitsubaNodeNormalMapBSDF,
    blend.MitsubaNodeBlendBSDF,
    mask.MitsubaNodeMaskBSDF,
    null.MitsubaNodeNullBSDF,
    principled.MitsubaNodePrincipledBSDF,
)

def register():
    register_node_categories('MITSUBA_MATERIAL_TREE', mitsuba_node_categories_material)

    for cls in classes:
        register_class(cls)

def unregister():
    for cls in classes:
        unregister_class(cls)

    unregister_node_categories('MITSUBA_MATERIAL_TREE')
