'''Registry of Mitsuba BSDF to Blender shader node converters.

Converter modules in this package register functions with
@material_converter('<plugin name>'). A converter receives a
MaterialBuilder and the Mitsuba properties of the BSDF, creates shader
nodes through the builder, and returns the output socket that represents
the BSDF. Nested BSDFs are converted with builder.convert_bsdf, which
never raises: failures are logged and produce a distinctive pink error
BSDF instead.

Texture plugins register with @texture_converter('<plugin name>') and
return the output socket of the node graph they build.
'''

import importlib
import pkgutil

import bpy

from ... import ConversionError

_material_converters = {}
_texture_converters = {}


def material_converter(*plugin_names):
    '''Register a converter for the given Mitsuba BSDF plugin names.'''
    def decorator(func):
        for plugin_name in plugin_names:
            _material_converters[plugin_name] = func
        return func
    return decorator


def texture_converter(*plugin_names):
    '''Register a converter for the given Mitsuba texture plugin names.'''
    def decorator(func):
        for plugin_name in plugin_names:
            _texture_converters[plugin_name] = func
        return func
    return decorator


ERROR_COLOR = (1.0, 0.0, 0.3, 1.0)


class MaterialBuilder:
    '''Builds a Blender shader node tree from Mitsuba properties.'''

    def __init__(self, mi_context, bl_mat):
        self.mi_context = mi_context
        self.bl_mat = bl_mat
        self.tree = bl_mat.node_tree

    def node(self, bl_idname):
        return self.tree.nodes.new(bl_idname)

    def link(self, from_socket, to_socket):
        self.tree.links.new(from_socket, to_socket)

    def child_props(self, node_id):
        '''The Mitsuba properties of a referenced scene node.'''
        return self.mi_context.mi_state.nodes[node_id].props

    def error_bsdf(self):
        '''A distinctive pink BSDF marking a failed conversion.'''
        node = self.node('ShaderNodeBsdfDiffuse')
        node.inputs['Color'].default_value = ERROR_COLOR
        return node.outputs['BSDF']

    def convert_bsdf(self, mi_props):
        '''Convert a BSDF into nodes; returns its shader output socket.
        Never raises: failures produce a warning and an error BSDF.'''
        plugin_name = mi_props.plugin_name()
        converter = _material_converters.get(plugin_name)
        try:
            if converter is None:
                raise ConversionError(f'Mitsuba BSDF type "{plugin_name}" '
                                      'is not supported')
            return converter(self, mi_props)
        except Exception as e:
            self.mi_context.log(
                f'Failed to convert Mitsuba BSDF '
                f'"{mi_props.id() or plugin_name}": {e}. '
                'Using an error material.', 'WARN')
            return self.error_bsdf()

    def convert_texture(self, node_id):
        '''Build nodes for a referenced texture; returns its output socket,
        or None (with a warning) if the texture type has no converter.'''
        mi_props = self.child_props(node_id)
        plugin_name = mi_props.plugin_name()
        converter = _texture_converters.get(plugin_name)
        if converter is None:
            self.mi_context.log(f'Mitsuba texture type "{plugin_name}" is '
                                'not supported.', 'WARN')
            return None
        return converter(self, mi_props)

    def set_float(self, socket, mi_props, name, default=None,
                  transform=None):
        '''Write a float property, a constant or a texture, into an input
        socket. `transform` is applied to constant values (e.g. roughness
        remapping).'''
        from mitsuba import Properties

        def assign(value):
            socket.default_value = transform(value) if transform else value

        if name not in mi_props:
            if default is not None:
                assign(default)
            return
        prop_type = mi_props.type(name)
        if prop_type == Properties.Type.Float:
            assign(mi_props[name])
        elif prop_type == Properties.Type.Color:
            rgb = list(mi_props[name])
            assign(0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2])
        elif prop_type == Properties.Type.ResolvedReference:
            source = self.convert_texture(mi_props[name].index())
            if source is not None:
                self.link(source, socket)
            elif default is not None:
                assign(default)
        else:
            self.mi_context.log(f'Property "{name}" of type {prop_type} '
                                'cannot be converted to a float.', 'WARN')
            if default is not None:
                assign(default)

    def set_color(self, socket, mi_props, name, default=None):
        '''Write a color property, a constant or a texture, into an input
        socket.'''
        from mitsuba import Properties
        if name not in mi_props:
            if default is not None:
                socket.default_value = _rgba(default)
            return
        prop_type = mi_props.type(name)
        if prop_type == Properties.Type.Color:
            socket.default_value = _rgba(list(mi_props[name]))
        elif prop_type == Properties.Type.Float:
            socket.default_value = _rgba([mi_props[name]] * 3)
        elif prop_type == Properties.Type.ResolvedReference:
            source = self.convert_texture(mi_props[name].index())
            if source is not None:
                self.link(source, socket)
            elif default is not None:
                socket.default_value = _rgba(default)
        else:
            self.mi_context.log(f'Property "{name}" of type {prop_type} '
                                'cannot be converted to a color.', 'WARN')
            if default is not None:
                socket.default_value = _rgba(default)


def convert_material(mi_context, mi_props, mi_emitter=None):
    '''Create a Blender material for a Mitsuba BSDF, wrapped in an emission
    shader when an area emitter is given. Never raises.'''
    name = mi_props.id() or f'Material-{mi_props.plugin_name()}'
    bl_mat = bpy.data.materials.new(name=name)
    bl_mat.use_nodes = True
    tree = bl_mat.node_tree
    tree.nodes.clear()
    output = tree.nodes.new('ShaderNodeOutputMaterial')

    builder = MaterialBuilder(mi_context, bl_mat)
    surface = builder.convert_bsdf(mi_props)
    if mi_emitter is not None:
        surface = _wrap_emitter(builder, surface, mi_emitter)
    builder.link(surface, output.inputs['Surface'])
    _layout_tree(tree, output)
    return bl_mat


def _rgba(color):
    color = list(color)
    return color + [1.0] * (4 - len(color))


def _wrap_emitter(builder, bsdf_socket, mi_emitter):
    '''Combine a BSDF output with an area emitter via an Add Shader.'''
    from ....io.importer import mi_spectra_utils
    radiance, strength = mi_spectra_utils.convert_radiance_property(
        builder.mi_context, mi_emitter, 'radiance', [1.0, 1.0, 1.0])

    emission = builder.node('ShaderNodeEmission')
    emission.inputs['Color'].default_value = _rgba(radiance)
    emission.inputs['Strength'].default_value = strength
    add = builder.node('ShaderNodeAddShader')
    builder.link(emission.outputs['Emission'], add.inputs[0])
    builder.link(bsdf_socket, add.inputs[1])
    return add.outputs['Shader']


def _layout_tree(tree, output):
    '''Arrange the nodes in columns by their link distance from the output.'''
    depths = {output: 0}
    stack = [output]
    while stack:
        node = stack.pop()
        for socket in node.inputs:
            for link in socket.links:
                child = link.from_node
                if depths.get(child, -1) < depths[node] + 1:
                    depths[child] = depths[node] + 1
                    stack.append(child)
    rows = {}
    for node, depth in depths.items():
        row = rows.get(depth, 0)
        node.location = (-300.0 * depth, -250.0 * row)
        rows[depth] = row + 1


# Converter modules register themselves when imported
for _module in pkgutil.iter_modules(__path__):
    if not _module.name.startswith('_'):
        importlib.import_module(f'.{_module.name}', __name__)
