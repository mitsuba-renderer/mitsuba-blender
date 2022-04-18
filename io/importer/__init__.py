import time

if "bpy" in locals():
    import importlib
    if "common" in locals():
        importlib.reload(common)
    if "materials" in locals():
        importlib.reload(materials)
    if "shapes" in locals():
        importlib.reload(shapes)
    if "cameras" in locals():
        importlib.reload(sensors)
    if "emitters" in locals():
        importlib.reload(emitters)
    if "world" in locals():
        importlib.reload(world)
    if "textures" in locals():
        importlib.reload(textures)
    if "mi_props_utils" in locals():
        importlib.reload(mi_props_utils)

import bpy

from . import common
from . import materials
from . import shapes
from . import emitters
from . import sensors
from . import world
from . import textures
from . import mi_props_utils

########################
##     Utilities      ##
########################

def _check_unqueried_props(mi_context, mi_cls, mi_props):
    for prop_name in mi_props.unqueried():
        mi_context.log(f'Mitsuba {mi_cls} property "{prop_name}" was not handled.', 'WARN')

def _convert_named_references(mi_context, mi_props, parent_node, type_filter=[]):
    for _, ref_id in mi_props.named_references():
        mi_child_cls, mi_child_props = mi_context.mi_scene_props.get_with_id(ref_id)
        assert mi_child_cls is not None and mi_child_props is not None
        if len(type_filter) == 0 or mi_child_cls in type_filter:
            child_node = mi_props_to_bl_data_node(mi_context, mi_child_cls, mi_child_props)
            if child_node is not None:
                parent_node.add_child(child_node)

########################
##  Scene convertion  ##
########################

def mi_scene_to_bl_node(mi_context, mi_props):
    node = common.create_blender_node(common.BlenderNodeType.SCENE, id=mi_props.id())
    # Convert all objects referenced by the scene
    # NOTE: Objects that are not referenced somewhere in the Mitsuba XML scene will
    #       not be loaded at all.
    _convert_named_references(mi_context, mi_props, node)

    return node

def mi_integrator_to_bl_node(mi_context, mi_props):
    # FIXME: Support nested integrators (AOVs)
    node = common.create_blender_node(common.BlenderNodeType.PROPERTIES, id=mi_props.id())
    # Convert dependencies if any
    _convert_named_references(mi_context, mi_props, node)

    return node

def mi_sensor_to_bl_node(mi_context, mi_props):
    node = common.create_blender_node(common.BlenderNodeType.OBJECT, id=mi_props.id())
    # Convert dependencies if any
    _convert_named_references(mi_context, mi_props, node)
    # Convert the camera
    bl_camera, world_matrix = sensors.mi_sensor_to_bl_camera(mi_context, mi_props)

    node.obj_type = common.BlenderObjectNodeType.CAMERA
    node.bl_data = bl_camera
    node.world_matrix = world_matrix
    return node

def mi_sampler_to_bl_node(mi_context, mi_props):
    node = common.create_blender_node(common.BlenderNodeType.PROPERTIES, id=mi_props.id())
    # Convert dependencies if any
    _convert_named_references(mi_context, mi_props, node)

    return node

def mi_rfilter_to_bl_node(mi_context, mi_props):
    node = common.create_blender_node(common.BlenderNodeType.PROPERTIES, id=mi_props.id())
    # Convert dependencies if any
    _convert_named_references(mi_context, mi_props, node)

    return node

def mi_film_to_bl_node(mi_context, mi_props):
    node = common.create_blender_node(common.BlenderNodeType.PROPERTIES, id=mi_props.id())
    # Convert dependencies if any
    _convert_named_references(mi_context, mi_props, node)

    return node

def mi_bsdf_to_bl_node(mi_context, mi_props, mi_emitter=None):
    node = common.create_blender_node(common.BlenderNodeType.MATERIAL, id=mi_props.id())
    # Parse referenced textures to ensure they are loaded before we parse the material
    _convert_named_references(mi_context, mi_props, node, type_filter=['Texture'])
    
    if mi_emitter is None:
        # If the BSDF is not emissive, we can look for it in the cache.
        bl_material = mi_context.get_bl_material(mi_props.id())
        if bl_material is None:
            bl_material = materials.mi_material_to_bl_material(mi_context, mi_props)
            if bl_material is None:
                return None
            mi_context.register_bl_material(mi_props.id(), bl_material)
    else:
        # If the BSDF is emissive, we don't use the cache value and create a new one everytime.
        bl_material = materials.mi_material_to_bl_material(mi_context, mi_props, mi_emitter=mi_emitter)

    node.bl_mat = bl_material
    return node

def mi_emitter_to_bl_node(mi_context, mi_props):
    # NOTE: Some Mitsuba emitters need to be imported as a Blender world material
    if world.should_convert_mi_emitter_to_bl_world(mi_props):
        node = common.create_blender_node(common.BlenderNodeType.WORLD, id=mi_props.id())
        # Convert dependencies if any
        _convert_named_references(mi_context, mi_props, node)

        bl_world = world.mi_emitter_to_bl_world(mi_context, mi_props)

        node.bl_world = bl_world
    else:
        node = common.create_blender_node(common.BlenderNodeType.OBJECT, id=mi_props.id())
        # Convert dependencies if any
        _convert_named_references(mi_context, mi_props, node)

        bl_light, world_matrix = emitters.mi_emitter_to_bl_light(mi_context, mi_props)
        
        node.obj_type = common.BlenderObjectNodeType.LIGHT
        node.bl_data = bl_light
        node.world_matrix = world_matrix
    return node

def mi_shape_to_bl_node(mi_context, mi_props):
    node = common.create_blender_node(common.BlenderNodeType.OBJECT, id=mi_props.id())
    
    mi_mats = mi_props_utils.named_references_with_class(mi_context, mi_props, 'BSDF')
    assert len(mi_mats) == 1
    mi_emitters = mi_props_utils.named_references_with_class(mi_context, mi_props, 'Emitter')
    assert len(mi_emitters) <= 1

    mi_mat_node = mi_bsdf_to_bl_node(mi_context, mi_mats[0], mi_emitter=mi_emitters[0] if len(mi_emitters) == 1 else None)
    node.add_child(mi_mat_node)

    # Convert the shape
    bl_shape, world_matrix = shapes.mi_shape_to_bl_shape(mi_context, mi_props)
    
    node.obj_type = common.BlenderObjectNodeType.SHAPE
    node.bl_data = bl_shape
    node.world_matrix = world_matrix
    return node

def mi_texture_to_bl_node(mi_context, mi_props):
    # We only parse bitmap textures
    if mi_props.plugin_name() != 'bitmap':
        return None

    node = common.create_blender_node(common.BlenderNodeType.IMAGE, id=mi_props.id())
    # Convert dependencies if any
    _convert_named_references(mi_context, mi_props, node)
    # Load the image
    bl_image = mi_context.get_bl_image(mi_props.id())
    if bl_image is None:
        bl_image = textures.mi_texture_to_bl_image(mi_context, mi_props)
        if bl_image is None:
            return None
        mi_context.register_bl_image(mi_props.id(), bl_image)
    
    node.bl_image = bl_image
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
    'Texture': mi_texture_to_bl_node,
    'ReconstructionFilter': mi_rfilter_to_bl_node,
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

def instantiate_bl_scene_node(mi_context, bl_node):
    for child_node in bl_node.children:
        if not instantiate_bl_data_node(mi_context, child_node):
            return False
    return True

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
    # TODO: Set Blender properties here
    return True

def instantiate_bl_material_node(mi_context, bl_node):
    # Nothing to do here.
    return True

def instantiate_bl_world_node(mi_context, bl_node):
    if mi_context.bl_scene.world is not None:
        mi_context.log(f'Multiple Blender worlds is not supported.', 'ERROR')
        return False
    mi_context.bl_scene.world = bl_node.bl_world
    return True

def instantiate_bl_image_node(mi_context, bl_node):
    # Nothing to do here.
    return True

_bl_node_instantiators = {
    common.BlenderNodeType.SCENE: instantiate_bl_scene_node,
    common.BlenderNodeType.MATERIAL: instantiate_bl_material_node,
    common.BlenderNodeType.OBJECT: instantiate_bl_object_node,
    common.BlenderNodeType.PROPERTIES: instantiate_bl_properties_node,
    common.BlenderNodeType.WORLD: instantiate_bl_world_node,
    common.BlenderNodeType.IMAGE: instantiate_bl_image_node,
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
    start_time = time.time()
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

    end_time = time.time()
    mi_context.log(f'Finished loading Mitsuba scene. Took {end_time-start_time:.2f}s.', 'INFO')

    return