from bpy.props import BoolProperty

from ..utils.nodetree import get_output_nodes

class MitsubaSocket:
    '''
    Base class for custom Mitsuba node sockets
    '''
    bl_label = ''

    color = (1, 1, 1, 1)
    slider = False

    @classmethod
    def is_input_connection_valid(cls, connected_socket):
        for valid_cls in cls.valid_inputs:
            if isinstance(connected_socket, valid_cls):
                return True
        return False

    def get_linked_node(self):
        if self.is_linked and len(self.links) > 0:
            return self.links[0].from_node
        return None

    def has_valid_state(self):
        # If this socket is linked, check that the connected
        # socket is of a valid type.
        if self.is_linked and len(self.links) > 0:
            link = self.links[0]
            if link and hasattr(self, 'valid_inputs'):
                if not self.is_input_connection_valid(link.from_socket):
                    return False
        return True

    def draw_prop(self, context, layout, node, text):
        layout.prop(self, 'default_value', text=text, slider=self.slider)

    def draw(self, context, layout, node, text):
        if not self.has_valid_state():
            layout.label(text='Wrong Input', icon='CANCEL')
            return

        has_default = hasattr(self, "default_value") and self.default_value is not None

        if self.is_output or self.is_linked or not has_default:
            layout.label(text=text)
        else:
            self.draw_prop(context, layout, node, text)

    def draw_color(self, context, node):
        return self.color

    def to_default_dict(self, export_context):
        '''
        Export the default value of a socket in a form the Mitsuba can understand
        (either a value or a dictionary for complex types).
        '''
        # Implement in subclasses
        raise RuntimeError(f'{self.bl_idname} default conversion not implemented')

    def to_dict(self, export_context):
        '''
        Convert this socket to a Mitsuba dictionary.
        '''
        if not self.has_valid_state():
            export_context.log('Cannot export material: Invalid socket state', 'ERROR')
            return None
        linked_node = self.get_linked_node()
        if linked_node is not None:
            # If a socket is connected, convert the connected node to a Mitsuba dictionary
            return linked_node.to_dict(export_context)
        if hasattr(self, 'default_value'):
            # If the socket is not connected and has a default value, convert it to a Mitsuba dictionary
            return self.to_default_dict(export_context)
        # Otherwise, this socket cannot be converted
        return None

class MitsubaNode:
    '''
    Base class for custom Mitsuba shader nodes
    '''
    bl_label = ''
    bl_width_default = 160

    @classmethod
    def poll(cls, tree):
        return tree.bl_idname == 'mitsuba_material_nodes'

    def init(self, context):
        # Error node color
        self.color = (1.0, 0.3, 0.3)

    def add_input(self, type, name, identifier='', default=None):
        input = self.inputs.new(type, name, identifier=identifier)
        if hasattr(input, 'default_value'):
            input.default_value = default
        return input

    def update(self):
        # Activate the error node color if a socket has an invalid state
        has_errors = False
        for socket in self.inputs:
            if hasattr(socket, 'has_valid_state') and not socket.has_valid_state():
                has_errors = True
        self.use_custom_color = has_errors

    def to_dict(self, export_context):
        # To implement in the subclasses
        raise RuntimeError(f'{self.bl_idname} conversion not implemented.')

class MitsubaNodeOutput(MitsubaNode):
    '''
    Shader node representing a Mitsuba material output
    '''
    def _update_active(output_node, context):
        if not output_node.is_active:
            output_node.is_active = True
        output_node.disable_other_outputs()

    is_active: BoolProperty(name='Active', default=True, update=_update_active)

    def init(self, context):
        super().init(context)
        self.disable_other_outputs()

    def draw_buttons(self, context, layout):
        layout.prop(self, 'is_active')

    def free(self):
        if not self.is_active:
            return

        node_tree = self.id_data
        if node_tree is None:
            return
        for node in get_output_nodes(node_tree):
            if node != self:
                node['is_active'] = True
                break

    def disable_other_outputs(self):
        node_tree = self.id_data
        if node_tree is None:
            return
        for node in get_output_nodes(node_tree):
            if node != self:
                node['is_active'] = False

class MitsubaNodeTree:
    '''
    Base class for custom Mitsuba shader node trees
    '''
    bl_label = ''

    @classmethod
    def poll(cls, context):
        return context.scene.render.engine == 'MITSUBA'
