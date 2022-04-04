import os

if "bpy" in locals():
    import importlib
    if "common" in locals():
        importlib.reload(common)
    if "materials" in locals():
        importlib.reload(materials)
    if "shapes" in locals():
        importlib.reload(shapes)
    if "cameras" in locals():
        importlib.reload(cameras)
    if "emitters" in locals():
        importlib.reload(emitters)

import bpy

from . import common
from . import materials
from . import shapes
from . import emitters
from . import cameras

########################
##     Utilities      ##
########################

def _check_unqueried_props(mi_context, mi_cls, mi_props):
    for prop_name in mi_props.unqueried():
        mi_context.log(f'Mitsuba {mi_cls} property "{prop_name}" was not handled.', 'WARN')

def _convert_named_references(mi_context, mi_props, parent_node):
    for _, ref_id in mi_props.named_references():
        mi_child_cls, mi_child_props = mi_context.mi_scene_props.get_with_id(ref_id)
        child_node = mi_props_to_bl_data_node(mi_context, mi_child_cls, mi_child_props)
        if child_node is not None:
            parent_node.add_child(child_node)

########################
##  Scene convertion  ##
########################

def mi_scene_to_bl_node(mi_context, mi_props):
    node = common.BlenderSceneNode(mi_props.id())
    _convert_named_references(mi_context, mi_props, node)
    return node

def mi_integrator_to_bl_node(mi_context, mi_props):
    # FIXME: Support nested integrators (AOVs)
    node = common.BlenderPropertiesNode('Integrator', mi_props, id=mi_props.id())
    return node

def mi_sensor_to_bl_node(mi_context, mi_props):
    bl_camera, world_matrix = cameras.mi_sensor_to_bl_camera(mi_context, mi_props)
    node = common.BlenderObjectNode(common.BlenderObjectNodeType.CAMERA, bl_camera, world_matrix, mi_props.id())
    _convert_named_references(mi_context, mi_props, node)
    return node

def mi_sampler_to_bl_node(mi_context, mi_props):
    node = common.BlenderPropertiesNode('Sampler', mi_props, id=mi_props.id())
    return node

def mi_film_to_bl_node(mi_context, mi_props):
    node = common.BlenderPropertiesNode('Film', mi_props, id=mi_props.id())
    return node

def mi_bsdf_to_bl_node(mi_context, mi_props):
    # FIXME: Support nested plugins
    bl_material = mi_context.get_bl_material(mi_props.id())
    if bl_material is None:
        bl_material = materials.mi_material_to_bl_material(mi_context, mi_props)
        if bl_material is None:
            return None
        mi_context.register_bl_material(mi_props.id(), bl_material)
    return common.BlenderMaterialNode(bl_material, id=mi_props.id())

def mi_emitter_to_bl_node(mi_context, mi_props):
    bl_light, world_matrix = emitters.mi_emitter_to_bl_light(mi_context, mi_props)
    node = common.BlenderObjectNode(common.BlenderObjectNodeType.LIGHT, bl_light, world_matrix, mi_props.id())
    return node

def mi_shape_to_bl_node(mi_context, mi_props):
    # FIXME: Support nested emitter/bsdf combination
    bl_shape, world_matrix = shapes.mi_shape_to_bl_shape(mi_context, mi_props)
    node = common.BlenderObjectNode(common.BlenderObjectNodeType.SHAPE, bl_shape, world_matrix, mi_props.id())
    _convert_named_references(mi_context, mi_props, node)
    return node

_bl_data_converters = {
    'Scene': mi_scene_to_bl_node,
    'Integrator': mi_integrator_to_bl_node,
    'Sensor': mi_sensor_to_bl_node,
    'Sampler': mi_sampler_to_bl_node,
    'Film': mi_film_to_bl_node,
    'BSDF': mi_bsdf_to_bl_node,
    'Emitter': mi_emitter_to_bl_node,
    'Shape': mi_shape_to_bl_node,
}

def mi_props_to_bl_data_node(mi_context, mi_cls, mi_props):
    if mi_cls not in _bl_data_converters:
        mi_context.log(f'Mitsuba class "{mi_cls}" not supported.', 'ERROR')
        return None
    node = _bl_data_converters[mi_cls](mi_context, mi_props)
    if node is None:
        mi_context.log(f'Failed to convert Mitsuba class "{mi_cls}".', 'ERROR')
        return None
    return node

#########################
## Scene instantiation ##
#########################

def instantiate_bl_shape_object_node(mi_context, bl_node):
    bl_obj = bpy.data.objects.new(bl_node.id, bl_node.bl_data)
    bl_obj.matrix_world = bl_node.world_matrix
    
    shape_has_material = False
    for child_node in bl_node.children:
        # NOTE: Mitsuba shapes support only one BSDF
        if child_node.type == common.BlenderNodeType.MATERIAL:
            shape_has_material = True
            bl_node.bl_data.materials.clear()
            bl_node.bl_data.materials.append(child_node.bl_mat)
            bl_obj.active_material_index = 0
            break

    if not shape_has_material:
        mi_context.log(f'Shape "{bl_node.id}" does not have a material. Using default diffuse.', 'WARN')

    mi_context.bl_collection.objects.link(bl_obj)

    return True

def instantiate_bl_camera_object_node(mi_context, bl_node):
    # FIXME: Move this for delayed instantiation as the whole scene needs to
    #        be created in order to support multiple camera settings.
    # FIXME: Handle child nodes
    bl_obj = bpy.data.objects.new(bl_node.id, bl_node.bl_data)
    bl_obj.matrix_world = bl_node.world_matrix

    mi_context.bl_collection.objects.link(bl_obj)
    mi_context.bl_scene.camera = bl_obj

    return True

def instantiate_bl_light_object_node(mi_context, bl_node):
    bl_obj = bpy.data.objects.new(bl_node.id, bl_node.bl_data)
    bl_obj.matrix_world = bl_node.world_matrix

    mi_context.bl_collection.objects.link(bl_obj)

    return True

_bl_object_node_instantiators = {
    common.BlenderObjectNodeType.SHAPE: instantiate_bl_shape_object_node,
    common.BlenderObjectNodeType.CAMERA: instantiate_bl_camera_object_node,
    common.BlenderObjectNodeType.LIGHT: instantiate_bl_light_object_node,
}

def instantiate_bl_object_node(mi_context, bl_node):
    node_obj_type = bl_node.obj_type
    if node_obj_type not in _bl_object_node_instantiators:
        mi_context.log(f'Unknown Blender object node type "{node_obj_type}".', 'ERROR')
        return False
    if not _bl_object_node_instantiators[node_obj_type](mi_context, bl_node):
        mi_context.log(f'Failed to instantiate Blender object node "{node_obj_type}".', 'ERROR')
        return False
    return True

def instantiate_bl_properties_node(mi_context, bl_node):
    return True

def instantiate_bl_scene_node(mi_context, bl_node):
    for child_node in bl_node.children:
        if not instantiate_bl_data_node(mi_context, child_node):
            return False
    return True

def instantiate_bl_material_node(mi_context, bl_node):
    # Nothing to do here.
    return True

_bl_node_instantiators = {
    common.BlenderNodeType.SCENE: instantiate_bl_scene_node,
    common.BlenderNodeType.MATERIAL: instantiate_bl_material_node,
    common.BlenderNodeType.OBJECT: instantiate_bl_object_node,
    common.BlenderNodeType.PROPERTIES: instantiate_bl_properties_node,
}

def instantiate_bl_data_node(mi_context, bl_node):
    node_type = bl_node.type
    if node_type not in _bl_node_instantiators:
        mi_context.log(f'Unknown Blender node type "{node_type}".', 'ERROR')
        return False
    if not _bl_node_instantiators[node_type](mi_context, bl_node):
        mi_context.log(f'Failed to instantiate Blender node "{node_type}".', 'ERROR')
        return False
    return True


#########################
##    Main loading     ##
#########################

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
    raw_props = xml_to_props(filepath)
    mi_scene_props = common.MitsubaSceneProperties(raw_props)
    mi_context = common.MitsubaSceneImportContext(bl_context, bl_scene, bl_collection, filepath, mi_scene_props, global_mat)

    _, mi_props = mi_scene_props.get_first_of_class('Scene')
    bl_scene_data_node = mi_props_to_bl_data_node(mi_context, 'Scene', mi_props)
    if bl_scene_data_node is None:
        mi_context.log('Failed to load Mitsuba scene', 'ERROR')
        return
    
    if not instantiate_bl_data_node(mi_context, bl_scene_data_node):
        mi_context.log('Failed to instantiate Blender scene', 'ERROR')
        return
    
    # Check that every property was accessed at least once as a sanity check
    for cls, prop in mi_scene_props:
        _check_unqueried_props(mi_context, cls, prop)

    return