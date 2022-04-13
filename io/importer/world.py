if "bpy" in locals():
    import importlib
    if "bl_material_utils" in locals():
        importlib.reload(bl_shader_utils)
    if "mi_spectra_utils" in locals():
        importlib.reload(mi_spectra_utils)
    if "bl_image_utils" in locals():
        importlib.reload(bl_image_utils)
    
import bpy

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
    'SRGBEmitterSpectrum': write_mi_srgb_emitter_spectrum
}

def write_mi_emitter_spectrum_object(mi_context, mi_obj, bl_world_wrap, radiance_socket_id, strength_socket_id, default=None):
    mi_obj_class_name = mi_obj.class_().name()
    if mi_obj_class_name not in _emitter_spectrum_object_writers:
        mi_context.log(f'Mitsuba object type "{mi_obj_class_name}" is not supported.', 'ERROR')
        return
    _emitter_spectrum_object_writers[mi_obj_class_name](mi_context, mi_obj, bl_world_wrap, radiance_socket_id, strength_socket_id, default)

def write_mi_world_radiance_property(mi_context, mi_emitter, mi_prop_name, bl_world_wrap, radiance_socket_id, strength_socket_id, default=None):
    from mitsuba import Properties
    if mi_emitter.has_property(mi_prop_name):
        mi_prop_type = mi_emitter.type(mi_prop_name)
        if mi_prop_type == Properties.Type.Color:
            color, strength = mi_spectra_utils.get_color_strength_from_radiance(list(mi_emitter.get(mi_prop_name, default)))
            bl_world_wrap.out_node.inputs[radiance_socket_id].default_value = bl_shader_utils.rgb_to_rgba(color)
            bl_world_wrap.out_node.inputs[strength_socket_id].default_value = strength
        elif mi_prop_type == Properties.Type.Object:
            mi_obj = mi_emitter.get(mi_prop_name)
            write_mi_emitter_spectrum_object(mi_context, mi_obj, bl_world_wrap, radiance_socket_id, strength_socket_id, default)
        else:
            mi_context.log(f'Material property "{mi_prop_name}" of type "{mi_prop_type}" cannot be converted to rgb.', 'ERROR')
    elif default is not None:
        color, strength = mi_spectra_utils.get_color_strength_from_radiance(default)
        bl_world_wrap.out_node.inputs[radiance_socket_id].default_value = bl_shader_utils.rgb_to_rgba(color)
        bl_world_wrap.out_node.inputs[strength_socket_id].default_value = strength
    else:
        mi_context.log(f'Emitter "{bl_world_wrap.id()}" does not have property "{mi_prop_name}".', 'ERROR')

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
        mi_context.log(f'Failed to load image file "{filepath}".', 'ERROR')
        return False
    bl_image.name = mi_emitter.id()
    # Create the background shader node
    bl_background = bl_world_wrap.ensure_node_type([out_socket_id], 'ShaderNodeBackground', 'Background')
    bl_background.inputs['Strength'].default_value = mi_emitter.get('scale', 1.0)
    # Create the environment texture node
    bl_environment = bl_world_wrap.ensure_node_type([out_socket_id, 'Color'], 'ShaderNodeTexEnvironment', 'Color')
    bl_environment.projection = 'EQUIRECTANGULAR'
    bl_environment.image = bl_image
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
        mi_context.log(f'Mitsuba Emitter type "{emitter_type}" not supported.', 'ERROR')
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
