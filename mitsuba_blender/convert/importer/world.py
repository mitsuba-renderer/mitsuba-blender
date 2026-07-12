'''Mitsuba environment emitter to Blender world conversion.

Constant emitters become a Background node, envmaps become an
Environment Texture (with a Mapping node reconstructing the to_world
rotation), and sunsky produces a placeholder with a warning.
'''

import math
import os

import bpy

from ..export.world import ENVMAP_COORDINATE_MAT
from ...io.importer import mi_spectra_utils
from ...io.importer.bl_transform_utils import mi_transform_to_bl_transform

ERROR_COLOR = (1.0, 0.0, 0.3, 1.0)


######################
##    Utilities     ##
######################

def _new_world(name):
    '''A fresh node-based world with a Background node wired to its
    output. Returns (bl_world, background node).'''
    bl_world = bpy.data.worlds.new(name=name)
    bl_world.use_nodes = True
    tree = bl_world.node_tree
    tree.nodes.clear()
    output = tree.nodes.new('ShaderNodeOutputWorld')
    output.location = (300, 0)
    background = tree.nodes.new('ShaderNodeBackground')
    tree.links.new(background.outputs['Background'],
                   output.inputs['Surface'])
    return bl_world, background


def _radiance_to_color_strength(mi_context, mi_props, name, default):
    from mitsuba import Properties
    if name in mi_props:
        prop_type = mi_props.type(name)
        if prop_type == Properties.Type.Color:
            return mi_spectra_utils.get_color_strength_from_radiance(
                list(mi_props[name]))
        if prop_type == Properties.Type.Float:
            return mi_spectra_utils.get_color_strength_from_radiance(
                [float(mi_props[name])] * 3)
        mi_context.log(f'World property "{name}" of type {prop_type} is '
                       'not supported. Using the default value.', 'WARN')
    return mi_spectra_utils.get_color_strength_from_radiance(list(default))


######################
##    Converters    ##
######################

def _convert_constant(mi_context, mi_props, background):
    color, strength = _radiance_to_color_strength(mi_context, mi_props,
                                                  'radiance', [1.0] * 3)
    background.inputs['Color'].default_value = list(color) + [1.0]
    background.inputs['Strength'].default_value = strength


def _convert_envmap(mi_context, mi_props, background):
    filename = mi_props.get('filename', '')
    filepath = filename if os.path.isabs(filename) \
        else os.path.join(mi_context.directory, filename)
    if not os.path.isfile(filepath):
        raise ValueError(f'cannot find the environment map "{filepath}"')
    bl_image = bpy.data.images.load(filepath, check_existing=True)

    background.inputs['Strength'].default_value = \
        float(mi_props.get('scale', 1.0))
    tree = background.id_data
    environment = tree.nodes.new('ShaderNodeTexEnvironment')
    environment.location = (-300, 0)
    environment.projection = 'EQUIRECTANGULAR'
    environment.image = bl_image
    tree.links.new(environment.outputs['Color'],
                   background.inputs['Color'])

    # Rebuild the to_world transform as a Mapping node, undoing the
    # equirectangular convention change applied by the exporter
    matrix = mi_context.mi_space_to_bl_space(
        mi_transform_to_bl_transform(mi_props.get('to_world', None))) \
        @ ENVMAP_COORDINATE_MAT.inverted()
    identity = all(math.isclose(matrix[i][j], float(i == j), abs_tol=1e-6)
                   for i in range(4) for j in range(4))
    if identity:
        return

    location, rotation, scale = matrix.decompose()
    mapping = tree.nodes.new('ShaderNodeMapping')
    mapping.location = (-500, 0)
    mapping.vector_type = 'TEXTURE'
    mapping.inputs['Location'].default_value = location
    mapping.inputs['Rotation'].default_value = rotation.to_euler()
    mapping.inputs['Scale'].default_value = scale
    coordinates = tree.nodes.new('ShaderNodeTexCoord')
    coordinates.location = (-700, 0)
    tree.links.new(coordinates.outputs['Generated'],
                   mapping.inputs['Vector'])
    tree.links.new(mapping.outputs['Vector'], environment.inputs['Vector'])


def _convert_sunsky(mi_context, mi_props, background):
    mi_context.log('Mitsuba sunsky emitters cannot be represented in '
                   'Blender. Using a plain sky-colored background.', 'WARN')
    background.inputs['Color'].default_value = (0.35, 0.55, 0.8, 1.0)


_converters = {
    'constant': _convert_constant,
    'envmap': _convert_envmap,
    'sunsky': _convert_sunsky,
}


######################
##   Main import    ##
######################

def should_convert_mi_emitter_to_bl_world(mi_props):
    '''Whether a Mitsuba emitter maps to a Blender world rather than a
    light object.'''
    return mi_props.plugin_name() in _converters


def mi_emitter_to_bl_world(mi_context, mi_props):
    '''Convert a Mitsuba environment emitter into a Blender world. Never
    raises: failures produce a warning and a distinctive error-colored
    background.'''
    plugin_name = mi_props.plugin_name()
    bl_world, background = _new_world(mi_props.id() or plugin_name)
    try:
        converter = _converters[plugin_name]
        converter(mi_context, mi_props, background)
    except Exception as e:
        mi_context.log(f'Failed to convert the "{plugin_name}" emitter to '
                       f'a world: {e}. Using an error background.', 'WARN')
        background.inputs['Color'].default_value = ERROR_COLOR
        background.inputs['Strength'].default_value = 1.0
    return bl_world


def create_default_bl_world():
    '''The default gray Blender world, recognized by the exporter's
    ignore_background option.'''
    bl_world, background = _new_world('World')
    background.inputs['Color'].default_value = \
        [0.05087608844041824] * 3 + [1.0]
    return bl_world
