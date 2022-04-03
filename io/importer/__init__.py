if "bpy" in locals():
    import importlib
    if "common" in locals():
        importlib.reload(common)
    if "materials" in locals():
        importlib.reload(materials)
    if "shapes" in locals():
        importlib.reload(shapes)

import bpy

from . import common
from . import materials
from . import shapes

########################
##   Scene loading    ##
########################

def load_mitsuba_scene(bl_context, bl_scene, bl_collection, filepath, global_mat):
    ''' Load a Mitsuba scene from an XML file into a Blender scene.
    
    Params
    ------
    bl_context: Blender context
    bl_scene: Blender scene
    bl_collection: Blender collection
    filepath: Path to the Mitsuba XML scene file
    global_mat: Axis conversion matrix
    '''
    # Load the Mitsuba XML and extract the objects' properties
    from mitsuba import xml_to_props
    mi_props = common.MitsubaSceneProperties(xml_to_props(filepath))
    mi_context = common.MitsubaSceneImportContext(bl_context, bl_scene, bl_collection, filepath, mi_props, global_mat)

    # Create all blender materials
    bl_error_mat = None
    for _, mi_mat in mi_props.with_class('BSDF'):
        bl_mat = materials.mi_material_to_bl_material(mi_context, mi_mat)
        if bl_mat is None:
            if bl_error_mat is None:
                bl_error_mat = materials.generate_error_material()
            mi_context.register_bl_material(mi_mat.id(), bl_error_mat)
        else:
            mi_context.register_bl_material(mi_mat.id(), bl_mat)


    # Create all blender shapes
    for _, mi_shape in mi_props.with_class('Shape'):
        shapes.mi_shape_to_bl_shape(mi_context, mi_shape)