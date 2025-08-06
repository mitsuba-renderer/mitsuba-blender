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
    if "renderer" in locals():
        importlib.reload(renderer)
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
from . import renderer
from .mi_props_utils import get_references_by_type

#####################
## Node conversion ##
#####################

def convert_mi_film(mi_context, node_id):
    from mitsuba import ObjectType

    mi_props = mi_context.mi_state.nodes[node_id].props
    if not renderer.apply_mi_film_properties(mi_context, mi_props):
        return None

    film_id = get_references_by_type(mi_context, mi_props, [ObjectType.ReconstructionFilter])
    if len(film_id) > 1:
        raise ValueError(f'Tried to import a film with multiple reconstruction filters. Mitsuba supports only one reconstruction filter per film.')
    elif len(film_id) == 1:
        convert_mi_node(mi_context, film_id[0])
    return True # ????

def convert_mi_rfilter(mi_context, node_id):
    mi_props = mi_context.mi_state.nodes[node_id].props
    #TODO: return what ?
    renderer.apply_mi_rfilter_properties(mi_context, mi_props)

def convert_mi_sampler(mi_context, node_id):
    mi_props = mi_context.mi_state.nodes[node_id].props
    renderer.apply_mi_sampler_properties(mi_context, mi_props)

def convert_mi_integrator(mi_context, node_id):
    mi_props = mi_context.mi_state.nodes[node_id].props
    # FIXME: Support nested integrators (AOVs)
    renderer.apply_mi_integrator_properties(mi_context, mi_props)

def convert_mi_emitter(mi_context, node_id):
    mi_props = mi_context.mi_state.nodes[node_id].props

    if world.should_convert_mi_emitter_to_bl_world(mi_props):
        bl_data = world.mi_emitter_to_bl_world(mi_context, mi_props)
        if mi_context.bl_scene.world is not None:
            mi_context.log(f'Multiple Blender worlds is not supported.', 'ERROR')
            return None
        mi_context.bl_scene.world = bl_data
    else:
        em_name = mi_props.id() if mi_props.id() else f'Emitter_{node_id}'
        bl_data, world_matrix = emitters.mi_emitter_to_bl_light(mi_context, mi_props)
        bl_obj = bpy.data.objects.new(em_name, bl_data)
        bl_obj.matrix_world = world_matrix

        mi_context.bl_collection.objects.link(bl_obj)

    return bl_data

def convert_mi_bsdf(mi_context, node_id, emitter_id=None):
    # Look up the material in the cache if it is not emissive
    if node_id in mi_context.bl_material_cache and emitter_id is None:
        return mi_context.bl_material_cache[node_id]

    mi_props = mi_context.mi_state.nodes[node_id].props
    bsdf_name = mi_props.id() if mi_props.id() else f'Material_{node_id}'
    
    if emitter_id is None:
        em_props = None
    else:
        em_props = mi_context.mi_state.nodes[emitter_id].props

    bl_material = materials.mi_material_to_bl_material(mi_context, mi_props, mi_emitter=em_props)
    if bl_material is None:
        mi_context.log(f'Failed to convert material "{bsdf_name}".', 'ERROR')
        return None

    # Store the material in the cache
    if emitter_id is None:
        mi_context.bl_material_cache[node_id] = bl_material
    return bl_material

def convert_mi_sensor(mi_context, node_id):
    from mitsuba import ObjectType
    mi_props = mi_context.mi_state.nodes[node_id].props
    camera_name = mi_props.id() if mi_props.id() else f'Camera_{node_id}'
    # Convert the camera
    bl_camera, world_matrix = sensors.mi_sensor_to_bl_camera(mi_context, mi_props)

    bl_obj = bpy.data.objects.new(camera_name, bl_camera)
    bl_obj.matrix_world = world_matrix

    mi_context.bl_collection.objects.link(bl_obj)
    mi_context.bl_scene.camera = bl_obj

    # Instantiate potential child sampler
    mi_children = get_references_by_type(mi_context, mi_props, [ObjectType.Sampler, ObjectType.Film])
    #TODO check correct number of samplers/films
    for child_id in mi_children:
        convert_mi_node(mi_context, child_id)

    return bl_obj

def convert_mi_shape(mi_context, node_id):
    from mitsuba import ObjectType
    mi_props = mi_context.mi_state.nodes[node_id].props
    shape_name = mi_props.id() if mi_props.id() else f'Shape_{node_id}'

    mi_emitters = get_references_by_type(mi_context, mi_props, [ObjectType.Emitter])
    if len(mi_emitters) > 1:
        raise ValueError(f'Tried to import a shape with multiple emitters. Mitsuba supports only one emitter per shape.')

    # Convert the shape
    bl_shape, world_matrix = shapes.mi_shape_to_bl_shape(mi_context, mi_props)
    bl_obj = bpy.data.objects.new(shape_name, bl_shape)
    bl_obj.matrix_world = world_matrix

    # Add a material
    bl_shape.materials.clear()
    mi_mats = get_references_by_type(mi_context, mi_props, [ObjectType.BSDF])
    if len(mi_mats) == 0:
        mi_context.log(f'Shape "{shape_name}" does not have a material. Using default diffuse.', 'WARN')
    elif len(mi_mats) > 1:
        mi_context.log(f'Shape "{shape_name}" has multiple materials. Only one is supported.', 'ERROR')
    else:
        # Make sure the material is converted
        if mi_emitters:
            em_id = mi_emitters[0]
        else:
            em_id = None
        bl_mat = convert_mi_bsdf(mi_context, mi_mats[0], emitter_id=em_id)
        bl_shape.materials.append(bl_mat)
        bl_obj.active_material_index = 0

    mi_context.bl_collection.objects.link(bl_obj)
    return bl_obj

def convert_mi_node(mi_context, node_id, extra_id=None):
    from mitsuba import ObjectType

    #TODO: generate convenient default object names
    mi_node = mi_context.mi_state.nodes[node_id]
    converters = {
        ObjectType.Shape: convert_mi_shape,
        ObjectType.Sensor: convert_mi_sensor,
        ObjectType.Integrator: convert_mi_integrator,
        ObjectType.Sampler: convert_mi_sampler,
        ObjectType.Film: convert_mi_film,
        ObjectType.Emitter: convert_mi_emitter,
        ObjectType.ReconstructionFilter: convert_mi_rfilter,
    }
    # TODO: maybe delay sensor instantiation ?
    if mi_node.type in converters:
        converters[mi_node.type](mi_context, node_id)

def convert_mi_scene(mi_context):
    from mitsuba import Properties
    for key, val in mi_context.mi_state.root.props.items():
        if isinstance(val, Properties.ResolvedReference):
            convert_mi_node(mi_context, val.index())

#########################
##    Main loading     ##
#########################

def load_mitsuba_scene(bl_context, bl_scene, bl_collection, filepath, global_mat, merge_shapes, merge_plugins):
    ''' Load a Mitsuba scene from an XML file into a Blender scene.
    
    Params
    ------
    bl_context: Blender context
    bl_scene: Blender scene
    bl_collection: Blender collection
    filepath: Path to the Mitsuba XML scene file
    global_mat: Axis conversion matrix
    merge_shapes: Whether to merge similar shapes (same material) into a single one
    merge_plugins: Whether to merge identical plugins (e.g. materials) into a single one
    '''
    #TODO: progress bar
    start_time = time.time()
    # Load the Mitsuba XML and extract the objects' properties
    import mitsuba as mi
    config = mi.parser.ParserConfig(mi.variant())
    config.merge_meshes = merge_shapes
    config.merge_equivalent = merge_plugins
    mi_state = mi.parser.parse_file(config, filepath)
    # Resolve all references and merge equivalent plugins if enabled
    mi.parser.transform_all(config, mi_state)
    mi_context = common.MitsubaSceneImportContext(bl_context, bl_scene, bl_collection, filepath, mi_state, global_mat)

    # Initialize the Mitsuba renderer inside of Blender
    renderer.init_mitsuba_renderer(mi_context)

    # Convert the Mitsuba scene state to a Blender scene
    #TODO: error checking
    convert_mi_scene(mi_context)

    # Instantiate a default Blender world if none was created
    if mi_context.bl_scene.world is None:
        mi_context.bl_scene.world = world.create_default_bl_world()
    
    # TODO: maybeCheck that every property was accessed at least once as a sanity check

    end_time = time.time()
    mi_context.log(f'Finished loading Mitsuba scene. Took {end_time-start_time:.2f}s.', 'INFO')

    return
