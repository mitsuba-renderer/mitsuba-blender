import bpy

from . import mi_spectra_utils
from . import bl_image_utils
from ..utils import nodetree
from ..utils import material

##############################
##  World property writers  ##
##############################

def write_mi_srgb_emitter_spectrum(mi_context, mi_obj, parent_node, radiance_socket_id, strength_socket_id, default=None):
    color, strength = mi_spectra_utils.convert_mi_srgb_emitter_spectrum(mi_obj, default)
    parent_node.set_property(radiance_socket_id, material.rgb_to_rgba(color))
    parent_node.set_property(strength_socket_id, strength)
    
_emitter_spectrum_object_writers = {
    'SRGBEmitterSpectrum': write_mi_srgb_emitter_spectrum
}

def write_mi_emitter_spectrum_object(mi_context, mi_obj, parent_node, radiance_socket_id, strength_socket_id, default=None):
    mi_obj_class_name = mi_obj.class_().name()
    if mi_obj_class_name not in _emitter_spectrum_object_writers:
        mi_context.log(f'Mitsuba object type "{mi_obj_class_name}" is not supported.', 'ERROR')
        return
    _emitter_spectrum_object_writers[mi_obj_class_name](mi_context, mi_obj, parent_node, radiance_socket_id, strength_socket_id, default)

def write_mi_world_radiance_property(mi_context, mi_emitter, mi_prop_name, parent_node, radiance_socket_id, strength_socket_id, default=None):
    from mitsuba import Properties
    if mi_emitter.has_property(mi_prop_name):
        mi_prop_type = mi_emitter.type(mi_prop_name)
        if mi_prop_type == Properties.Type.Color:
            color, strength = mi_spectra_utils.get_color_strength_from_radiance(list(mi_emitter.get(mi_prop_name, default)))
            parent_node.set_property(radiance_socket_id, material.rgb_to_rgba(color))
            parent_node.set_property(strength_socket_id, strength)
        elif mi_prop_type == Properties.Type.Object:
            mi_obj = mi_emitter.get(mi_prop_name)
            write_mi_emitter_spectrum_object(mi_context, mi_obj, parent_node, radiance_socket_id, strength_socket_id, default)
        else:
            mi_context.log(f'Material property "{mi_prop_name}" of type "{mi_prop_type}" cannot be converted to rgb.', 'ERROR')
    elif default is not None:
        color, strength = mi_spectra_utils.get_color_strength_from_radiance(default)
        parent_node.set_property(radiance_socket_id, material.rgb_to_rgba(color))
        parent_node.set_property(strength_socket_id, strength)
    else:
        mi_context.log(f'Emitter "{mi_emitter.id()}" does not have property "{mi_prop_name}".', 'ERROR')

######################
##     Writers      ##
######################

def write_mi_constant_emitter(mi_context, mi_emitter, parent_node, in_socket_id):
    background_node = parent_node.create_linked('ShaderNodeBackground', in_socket_id, out_socket_id='Background')
    write_mi_world_radiance_property(mi_context, mi_emitter, 'radiance', background_node, 'Color', 'Strength', [0.8, 0.8, 0.8])
    return True

def write_mi_envmap_emitter(mi_context, mi_emitter, parent_node, in_socket_id):
    # Load the environment texture
    filepath = mi_context.resolve_scene_relative_path(mi_emitter.get('filename'))
    bl_image = bl_image_utils.load_bl_image_from_filepath(mi_context, filepath, is_data=False)
    if bl_image is None:
        mi_context.log(f'Failed to load image file "{filepath}".', 'ERROR')
        return False
    bl_image.name = mi_emitter.id()
    # Create the background shader node
    background_node = parent_node.create_linked('ShaderNodeBackground', in_socket_id, out_socket_id='Background')
    background_node.set_property('Strength', mi_emitter.get('scale', 1.0))
    # Create the environment texture node
    environment_node = background_node.create_linked('ShaderNodeTexEnvironment', 'Color', out_socket_id='Color')
    environment_node.set_property('projection', 'EQUIRECTANGULAR')
    environment_node.set_property('image', bl_image)
    # FIXME: Handle texture coordinate transforms
    return True

######################
##   Main import    ##
######################

def write_error_world(parent_node, in_socket_id):
    ''' Write a Blender error world that can be applied whenever
    a Mitsuba emitter cannot be loaded.
    '''
    background_node = parent_node.create_linked('ShaderNodeBackground', in_socket_id, out_socket_id='Background')
    background_node.set_property('Color', material.rgb_to_rgba(1.0, 0.0, 0.3))

_world_writers = {
    'constant': write_mi_constant_emitter,
    'envmap': write_mi_envmap_emitter,
}

def write_mi_emitter(mi_context, mi_emitter, parent_node, in_socket_id):
    ''' Write a Mitsuba emitter in a node graph starting at a specific
    node in the shader graph.
    '''
    emitter_type = mi_emitter.plugin_name()
    if emitter_type not in _world_writers:
        mi_context.log(f'Mitsuba Emitter type "{emitter_type}" not supported.', 'ERROR')
        return

    if not _world_writers[emitter_type](mi_context, mi_emitter, parent_node, in_socket_id):
        write_error_world(parent_node, in_socket_id)

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
    node_tree = nodetree.NodeTreeWrapper.init_cycles_world(bl_world)
    node_tree.clear()
    output_node = node_tree.create_node('ShaderNodeOutputWorld')
    in_socket_id = 'Surface'

    # Write the Mitsuba emitter to the world output
    write_mi_emitter(mi_context, mi_emitter, output_node, in_socket_id)

    # Format the shader node graph
    node_tree.prettify()

    return bl_world

def should_convert_mi_emitter_to_bl_world(mi_emitter):
    ''' Return whether a Mitsuba emitter should be converted to
    a Blender world.
    '''
    return mi_emitter.plugin_name() in _world_writers

def create_default_bl_world():
    ''' Create the default Blender world '''
    bl_world = bpy.data.worlds.new(name='World')
    node_tree = nodetree.NodeTreeWrapper.init_cycles_world(bl_world)
    node_tree.clear()
    output_node = node_tree.create_node('ShaderNodeOutputWorld')
    background_node = output_node.create_linked('ShaderNodeBackground', 'Surface', out_socket_id='Background')
    # NOTE: This is the default Blender background color for worlds. This is required in order to be
    #       compatible with the exporter and the 'ignore_background' property
    background_node.set_property('Color', material.rgb_to_rgba([0.05087608844041824]*3))
    
    node_tree.prettify()
    
    return bl_world
