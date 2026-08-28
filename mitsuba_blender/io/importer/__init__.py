import time

import bpy

from . import common
from ...convert.importer import camera
from ...convert.importer import lights
from ...convert.importer import materials
from ...convert.importer import mesh as shapes
from ...convert.importer import world
from . import renderer
from .mi_props_utils import get_references_by_type

#####################
## Node conversion ##
#####################

def convert_mi_film(mi_context, node_id):
    from mitsuba import ObjectType

    if not mi_context.import_render_settings:
        return None
    mi_props = mi_context.mi_state.nodes[node_id].props
    if not renderer.apply_mi_film_properties(mi_context, mi_props):
        return None

    rfilter_ids = get_references_by_type(mi_context, mi_props, [ObjectType.ReconstructionFilter])
    if len(rfilter_ids) > 1:
        mi_context.log('Film has multiple reconstruction filters. Mitsuba '
                       'supports only one per film; using the first.', 'ERROR')
    if rfilter_ids:
        convert_mi_node(mi_context, rfilter_ids[0])
    return True

def convert_mi_rfilter(mi_context, node_id):
    if not mi_context.import_render_settings:
        return
    mi_props = mi_context.mi_state.nodes[node_id].props
    renderer.apply_mi_rfilter_properties(mi_context, mi_props)

def convert_mi_sampler(mi_context, node_id):
    if not mi_context.import_render_settings:
        return
    mi_props = mi_context.mi_state.nodes[node_id].props
    renderer.apply_mi_sampler_properties(mi_context, mi_props)

def convert_mi_integrator(mi_context, node_id):
    if not mi_context.import_render_settings:
        return
    mi_props = mi_context.mi_state.nodes[node_id].props
    renderer.apply_mi_integrator_properties(mi_context, mi_props)

def convert_mi_emitter(mi_context, node_id):
    mi_props = mi_context.mi_state.nodes[node_id].props

    if world.should_convert_mi_emitter_to_bl_world(mi_props):
        bl_data = world.mi_emitter_to_bl_world(mi_context, mi_props)
        if mi_context.bl_scene.world is not None:
            mi_context.log('Multiple Blender worlds are not supported.', 'ERROR')
            return None
        mi_context.bl_scene.world = bl_data
    else:
        em_name = mi_props.id() if mi_props.id() else f'Emitter_{node_id}'
        result = lights.mi_emitter_to_bl_light(mi_context, mi_props)
        if result is None:
            return None
        bl_data, world_matrix = result
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

    bl_material = materials.convert_material(mi_context, mi_props, mi_emitter=em_props)
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
    result = camera.mi_sensor_to_bl_camera(mi_context, mi_props)
    if result is None:
        return None
    bl_camera, world_matrix = result

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

    # The merge_meshes parser transform wraps the top-level shapes in a
    # merge node; convert its children individually
    if mi_props.plugin_name() == 'merge':
        for child_id in get_references_by_type(mi_context, mi_props,
                                               [ObjectType.Shape]):
            convert_mi_node(mi_context, child_id)
        return None

    shape_name = mi_props.id() if mi_props.id() else f'Shape_{node_id}'

    mi_emitters = get_references_by_type(mi_context, mi_props, [ObjectType.Emitter])
    if len(mi_emitters) > 1:
        mi_context.log(f'Shape "{shape_name}" has multiple emitters. Mitsuba '
                       'supports only one per shape; using the first.', 'ERROR')
        mi_emitters = mi_emitters[:1]

    # A supported shape that only carries an area emitter (no BSDF or a
    # null one) is a light source and comes back as a real Blender light
    mi_mats = get_references_by_type(mi_context, mi_props, [ObjectType.BSDF])
    if mi_emitters and lights.can_convert_area_emitter(mi_props) \
            and (not mi_mats or (len(mi_mats) == 1 and
                 mi_context.mi_state.nodes[mi_mats[0]].props.plugin_name() == 'null')):
        em_props = mi_context.mi_state.nodes[mi_emitters[0]].props
        result = lights.mi_area_emitter_to_bl_light(mi_context, em_props, mi_props)
        if result is not None:
            bl_light, world_matrix = result
            bl_obj = bpy.data.objects.new(shape_name, bl_light)
            bl_obj.matrix_world = world_matrix
            mi_context.bl_collection.objects.link(bl_obj)
            return bl_obj

    # Convert the shape
    result = shapes.mi_shape_to_bl_shape(mi_context, mi_props)
    if result is None:
        # An empty placeholder mesh keeps the object in the scene so the
        # user can see what failed to import.
        from mathutils import Matrix
        result = bpy.data.meshes.new(shape_name), Matrix()
    bl_shape, world_matrix = result
    bl_obj = bpy.data.objects.new(shape_name, bl_shape)
    bl_obj.matrix_world = world_matrix

    # Add a material
    bl_shape.materials.clear()
    em_id = mi_emitters[0] if mi_emitters else None
    bl_mat = None
    if len(mi_mats) > 1:
        mi_context.log(f'Shape "{shape_name}" has multiple materials. Only one is supported.', 'ERROR')
    elif len(mi_mats) == 1:
        bl_mat = convert_mi_bsdf(mi_context, mi_mats[0], emitter_id=em_id)
    elif em_id is not None:
        # An emissive shape without a BSDF still needs a Blender material
        # to hold its emission shader.
        from mitsuba import Properties
        mi_null = Properties('null')
        mi_null.set_id(f'{shape_name}-emitter')
        em_props = mi_context.mi_state.nodes[em_id].props
        bl_mat = materials.convert_material(mi_context, mi_null, mi_emitter=em_props)
    else:
        mi_context.log(f'Shape "{shape_name}" does not have a material. Using default diffuse.', 'WARN')

    if bl_mat is not None:
        bl_shape.materials.append(bl_mat)
        bl_obj.active_material_index = 0

    mi_context.bl_collection.objects.link(bl_obj)
    return bl_obj

def convert_mi_node(mi_context, node_id):
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
        # An unsupported or broken piece of content must never abort the
        # whole import
        try:
            converters[mi_node.type](mi_context, node_id)
        except Exception as e:
            mi_props = mi_node.props
            mi_context.log(f'Failed to convert Mitsuba object '
                           f'"{mi_props.id() or mi_props.plugin_name()}": '
                           f'{e}.', 'ERROR')

def convert_mi_scene(mi_context):
    from mitsuba import ObjectType, Properties
    # Samplers, films and rfilters are only converted as sensor children,
    # where a camera exists to receive their settings
    deferred = (ObjectType.Sampler, ObjectType.Film,
                ObjectType.ReconstructionFilter)
    for key, val in mi_context.mi_state.root.props.items():
        if isinstance(val, Properties.ResolvedReference):
            if mi_context.mi_state.nodes[val.index()].type in deferred:
                continue
            convert_mi_node(mi_context, val.index())

#########################
##    Main loading     ##
#########################

def parse_mitsuba_scene(filepath, merge_shapes, merge_plugins):
    ''' Parse a Mitsuba XML file and resolve all references. Raises on
    malformed input, so callers can parse before touching the Blender scene.

    The returned state carries a file resolver covering the scene directory
    and any <path> directories, which the converters use to locate files.
    '''
    import mitsuba as mi
    config = mi.parser.ParserConfig(mi.variant())
    config.merge_meshes = merge_shapes
    config.merge_equivalent = merge_plugins
    mi_state = mi.parser.parse_file(config, filepath)
    # Resolve all references and merge equivalent plugins if enabled
    mi.parser.transform_all(config, mi_state)
    return mi_state

def load_mitsuba_scene(bl_scene, bl_collection, filepath, global_mat, merge_shapes, merge_plugins,
                       import_render_settings=False, mi_state=None):
    ''' Load a Mitsuba scene from an XML file into a Blender scene.

    Params
    ------
    bl_scene: Blender scene
    bl_collection: Blender collection
    filepath: Path to the Mitsuba XML scene file
    global_mat: Axis conversion matrix
    merge_shapes: Whether to merge similar shapes (same material) into a single one
    merge_plugins: Whether to merge identical plugins (e.g. materials) into a single one
    import_render_settings: Whether to apply the scene's integrator, sampler,
        reconstruction filter and film settings to the Mitsuba render properties
    mi_state: Parser state from parse_mitsuba_scene; the file is parsed here
        when omitted

    Returns
    -------
    The list of warnings collected during the import.
    '''
    #TODO: progress bar
    start_time = time.time()
    if mi_state is None:
        mi_state = parse_mitsuba_scene(filepath, merge_shapes, merge_plugins)
    mi_context = common.MitsubaSceneImportContext(bl_scene, bl_collection, filepath, mi_state, global_mat,
                                                  import_render_settings)

    # Select the Mitsuba variant used for rendering
    renderer.init_mitsuba_variant(mi_context)

    # Convert the Mitsuba scene state to a Blender scene
    #TODO: error checking
    convert_mi_scene(mi_context)

    # Instantiate a default Blender world if none was created
    if mi_context.bl_scene.world is None:
        mi_context.bl_scene.world = world.create_default_bl_world()

    # TODO: maybeCheck that every property was accessed at least once as a sanity check

    end_time = time.time()
    mi_context.log(f'Finished loading Mitsuba scene. Took {end_time-start_time:.2f}s.', 'INFO')

    return mi_context.warnings
