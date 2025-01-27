import bpy

from .. import logging
from . import bl_shader_utils
from . import mi_spectra_utils
from . import bl_image_utils

##############################
##  World property writers  ##
##############################

def write_mi_srgb_emitter_spectrum(mi_context, mi_obj, bl_world_wrap, radiance_socket_id, strength_socket_id, default=None):
    color, strength = mi_spectra_utils.convert_mi_srgb_emitter_spectrum(mi_obj, default)
    bl_world_wrap.out_node.inputs[radiance_socket_id].default_value = bl_shader_utils.rgb_to_rgba(color)
    bl_world_wrap.out_node.inputs[strength_socket_id].default_value = strength

_emitter_spectrum_object_writers = {
    'SRGBEmitterSpectrum':     write_mi_srgb_emitter_spectrum,
    'SRGBReflectanceSpectrum': write_mi_srgb_emitter_spectrum
}

def write_mi_emitter_spectrum_object(mi_context, mi_obj, bl_world_wrap, radiance_socket_id, strength_socket_id, default=None):
    mi_obj_class_name = mi_obj.class_().name()
    if mi_obj_class_name not in _emitter_spectrum_object_writers:
        logging.error(f'Mitsuba object type "{mi_obj_class_name}" is not supported.')
        return
    _emitter_spectrum_object_writers[mi_obj_class_name](mi_context, mi_obj, bl_world_wrap, radiance_socket_id, strength_socket_id, default)

def write_mi_world_radiance_property(mi_context, mi_emitter, mi_prop_name, bl_world_wrap, radiance_socket_id, strength_socket_id, default=None):
    import mitsuba as mi
    if mi_emitter.has_property(mi_prop_name):
        mi_prop_type = mi_emitter.type(mi_prop_name)
        if mi_prop_type == mi.Properties.Type.Color:
            color, strength = mi_spectra_utils.get_color_strength_from_radiance(list(mi_emitter.get(mi_prop_name, default)))
            bl_world_wrap.out_node.inputs[radiance_socket_id].default_value = bl_shader_utils.rgb_to_rgba(color)
            bl_world_wrap.out_node.inputs[strength_socket_id].default_value = strength
        elif mi_prop_type == mi.Properties.Type.Object:
            mi_obj = mi_emitter.get(mi_prop_name)
            write_mi_emitter_spectrum_object(mi_context, mi_obj, bl_world_wrap, radiance_socket_id, strength_socket_id, default)
        elif mi_prop_type == mi.Properties.Type.NamedReference:
            ref_id = mi_emitter.get(mi_prop_name)
            mi_texture = mi_context.mi_scene_props.get_with_id_and_class(ref_id, 'Texture')
            assert mi_texture is not None
            if mi_texture.plugin_name() == 'uniform':
                bl_world_wrap.out_node.inputs[radiance_socket_id].default_value = [1.0, 1.0, 1.0, 1.0]
                bl_world_wrap.out_node.inputs[strength_socket_id].default_value = mi_texture.get('value')
        else:
            logging.error(f'Material property "{mi_prop_name}" of type "{mi_prop_type}" cannot be converted to rgb.')
    elif default is not None:
        color, strength = mi_spectra_utils.get_color_strength_from_radiance(default)
        bl_world_wrap.out_node.inputs[radiance_socket_id].default_value = bl_shader_utils.rgb_to_rgba(color)
        bl_world_wrap.out_node.inputs[strength_socket_id].default_value = strength
    else:
        logging.error(f'Emitter "{bl_world_wrap.id()}" does not have property "{mi_prop_name}".')

######################
##     Writers      ##
######################

def write_mi_constant_emitter(mi_context, mi_emitter, bl_world_wrap, out_socket_id):
    bl_background = bl_world_wrap.ensure_node_type([out_socket_id], 'ShaderNodeBackground', 'Background')
    bl_background_wrap = bl_shader_utils.NodeWorldWrapper(bl_world_wrap.bl_world, out_node=bl_background)
    write_mi_world_radiance_property(mi_context, mi_emitter, 'radiance', bl_background_wrap, 'Color', 'Strength', [0.8, 0.8, 0.8])
    return True

def write_mi_envmap_emitter(mi_context, mi_emitter, bl_world_wrap, out_socket_id):
    # Load the environment texture
    filepath = mi_context.resolve_scene_relative_path(mi_emitter.get('filename'))
    bl_image = bl_image_utils.load_bl_image_from_filepath(mi_context, filepath, is_data=False)
    if bl_image is None:
        logging.error(f'Failed to load image file "{filepath}".')
        return False
    bl_image.name = mi_emitter.id()
    # Create the background shader node
    bl_background = bl_world_wrap.ensure_node_type([out_socket_id], 'ShaderNodeBackground', 'Background')
    bl_background.inputs['Strength'].default_value = mi_emitter.get('scale', 1.0)
    # Create the environment texture node
    bl_environment = bl_world_wrap.ensure_node_type([out_socket_id, 'Color'], 'ShaderNodeTexEnvironment', 'Color')
    bl_environment.projection = 'EQUIRECTANGULAR'
    bl_environment.image = bl_image

    world_matrix = mi_emitter.get('to_world', None)
    if not world_matrix is None:
        import drjit as dr
        euler = dr.quat_to_euler(dr.matrix_to_quat(world_matrix.matrix))

        # TODO Why do we need this?
        euler[2] -= dr.pi / 2.0

        bl_texcoord = bl_world_wrap.tree.nodes.new(type='ShaderNodeTexCoord')
        bl_mapping  = bl_world_wrap.tree.nodes.new(type='ShaderNodeMapping')
        bl_world_wrap.tree.links.new(bl_texcoord.outputs[0], bl_mapping.inputs[0])
        bl_world_wrap.tree.links.new(bl_mapping.outputs[0],  bl_environment.inputs[0])

        bl_mapping.vector_type = 'TEXTURE'
        bl_mapping.inputs['Rotation'].default_value = list(euler)

    return True

######################
##   Main import    ##
######################

def write_bl_error_world(bl_world_wrap, out_socket_id):
    ''' Write a Blender error world that can be applied whenever
    a Mitsuba emitter cannot be loaded.
    '''
    bl_background = bl_world_wrap.ensure_node_type([out_socket_id], 'ShaderNodeBackground', 'Background')
    bl_background.inputs['Color'].default_value = [1.0, 0.0, 0.3, 1.0]

_world_writers = {
    'constant': write_mi_constant_emitter,
    'envmap': write_mi_envmap_emitter,
}

def write_mi_emitter_to_node_graph(mi_context, mi_emitter, bl_world_wrap, out_socket_id):
    ''' Write a Mitsuba emitter in a node graph starting at a specific
    node in the shader graph.
    '''
    emitter_type = mi_emitter.plugin_name()
    if emitter_type not in _world_writers:
        logging.error(f'Mitsuba Emitter type "{emitter_type}" not supported.')
        return

    if not _world_writers[emitter_type](mi_context, mi_emitter, bl_world_wrap, out_socket_id):
        write_bl_error_world(bl_world_wrap, out_socket_id)

def mi_emitter_to_bl_world(mi_context, mi_emitter):
    ''' Create a Blender node tree representing a given Mitsuba emitter

    Params
    ------
    mi_context : Mitsuba import context
    mi_emitter : Mitsuba emitter properties

    Returns
    -------
    The newly created Blender world
    '''
    bl_world = bpy.data.worlds.new(name=mi_emitter.id())
    bl_world_wrap = bl_shader_utils.NodeWorldWrapper(bl_world, init_empty=True)

    # Write the Mitsuba emitter to the world output
    write_mi_emitter_to_node_graph(mi_context, mi_emitter, bl_world_wrap, 'Surface')

    # Format the shader node graph
    bl_world_wrap.format_node_tree()

    return bl_world

def should_convert_mi_emitter_to_bl_world(mi_emitter):
    ''' Return whether a Mitsuba emitter should be converted to
    a Blender world.
    '''
    return mi_emitter.plugin_name() in _world_writers

def create_default_bl_world():
    ''' Create the default Blender world '''
    bl_world = bpy.data.worlds.new(name='World')
    bl_world_wrap = bl_shader_utils.NodeWorldWrapper(bl_world, init_empty=True)
    bl_background = bl_world_wrap.ensure_node_type(['Surface'], 'ShaderNodeBackground', 'Background')
    # NOTE: This is the default Blender background color for worlds. This is required in order to be
    #       compatible with the exporter and the 'export_default_background' property
    bl_background.inputs['Color'].default_value = [0.05087608844041824]*3 + [1.0]
    bl_world_wrap.format_node_tree()
    return bl_world
