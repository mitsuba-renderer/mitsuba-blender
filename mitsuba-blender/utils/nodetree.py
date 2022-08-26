import bpy
from collections import OrderedDict

def make_mitsuba_node_tree_name(bl_mat):
    return f'Nodes_{bl_mat.name}'

NODE_TREE_TYPE_TO_OUTPUT_NODE_TYPE = {
    'mitsuba_material_nodes': 'MitsubaNodeOutputMaterial',
    'mitsuba_world_nodes': 'MitsubaNodeOutputWorld',
}

def get_active_output(node_tree):
    output_node_type = NODE_TREE_TYPE_TO_OUTPUT_NODE_TYPE[node_tree.bl_idname]
    for node in node_tree.nodes:
        node_type = getattr(node, 'bl_idname', None)
        if node_type == output_node_type and node.is_active:
            return node
    return None

def get_output_nodes(node_tree):
    output_node_type = NODE_TREE_TYPE_TO_OUTPUT_NODE_TYPE[node_tree.bl_idname]
    nodes = []
    for node in node_tree.nodes:
        node_type = getattr(node, 'bl_idname', None)
        if node_type == output_node_type:
            nodes.append(node)
    return nodes

class NodeWrapper:
    ''' Utility wrapper around a Blender shader node '''
    def __init__(self, node_tree, node):
        self.node_tree = node_tree
        self.node = node

    def _get_socket_by_id(sockets, socket_id):
        for socket in sockets:
            if socket.identifier == socket_id:
                return socket
        return None
    
    def find_output_socket(self, out_socket_id=''):
        '''
        Find a suitable output socket for the given socket ID.
        '''
        outputs_count = len(self.node.outputs)
        if outputs_count == 0:
            raise RuntimeError('Node has no output.')
        if out_socket_id == '' and outputs_count > 1:
            raise RuntimeError(f'Cannot infer output socket. Node has {outputs_count} outputs.')
        out_socket = self.node.outputs[0]
        if out_socket_id != '':
            out_socket = NodeWrapper._get_socket_by_id(self.node.outputs, out_socket_id)
            if out_socket is None:
                raise RuntimeError(f'Cannot find output node "{out_socket_id}".')
        return out_socket

    def find_input_socket(self, in_socket_id):
        in_socket = NodeWrapper._get_socket_by_id(self.node.inputs, in_socket_id)
        if in_socket is None:
            raise RuntimeError(f'Cannot find input node "{in_socket_id}".')
        return in_socket

    def link_to(self, other_node, in_socket_id, out_socket_id=''):
        '''
        Link the output of this node to the input of another.
        '''
        out_socket = self.find_output_socket(out_socket_id)
        in_socket = other_node.find_input_socket(in_socket_id)
        if in_socket.is_linked:
            raise RuntimeError(f'Input socket "{in_socket_id}" is already linked.')
        self.node_tree.node_tree.links.new(out_socket, in_socket)

    def create_linked(self, other_type, in_socket_id, out_socket_id=''):
        '''
        Create a new node and link it to one input of this node
        '''
        other_node = self.node_tree.create_node(other_type)
        other_node.link_to(self, in_socket_id, out_socket_id)
        return other_node

    def delete_linked(self):
        '''
        Delete all nodes connected to the inputs of this node
        '''
        for input in self.node.inputs:
            if input.is_linked:
                for link in input.links:
                    node = NodeWrapper(self.node_tree, link.from_node)
                    node.delete_linked()
                    self.node_tree.delete_node(node)

    def set_property(self, property_name, value):
        '''
        Set the value of either a node's property or input socket.
        '''
        in_socket = NodeWrapper._get_socket_by_id(self.node.inputs, property_name)
        if hasattr(self.node, property_name):
            if in_socket is not None:
                raise RuntimeError(f'Property "{property_name}" is ambiguous with similarly named socket.')
            setattr(self.node, property_name, value)
        elif in_socket is None:
            raise RuntimeError(f'Node "{self.node.bl_idname}" does not have a property or socket with id "{property_name}".')
        else:
            if not hasattr(in_socket, 'default_value'):
                raise RuntimeError(f'Socket "{property_name}" cannot hold a value.')
            in_socket.default_value = value

class NodeTreeWrapper:
    ''' Utility wrapper around a Blender node tree '''
    def __init__(self, node_tree):
        self.node_tree = node_tree

    @staticmethod
    def init_cycles_material(bl_mat):
        if not bl_mat.use_nodes:
            bl_mat.use_nodes = True
        return NodeTreeWrapper(bl_mat.node_tree)

    @staticmethod
    def init_cycles_world(bl_world):
        if not bl_world.use_nodes:
            bl_world.use_nodes = True
        return NodeTreeWrapper(bl_world.node_tree)

    @staticmethod
    def init_mitsuba_material(bl_mat):
        node_tree = bl_mat.mitsuba.node_tree
        if node_tree is None:
            node_tree = bpy.data.node_groups.new(name=make_mitsuba_node_tree_name(bl_mat), type='mitsuba_material_nodes')
            bl_mat.mitsuba.node_tree = node_tree
        return NodeTreeWrapper(node_tree)

    def clear(self):
        for node in self.node_tree.nodes:
            self.node_tree.nodes.remove(node)

    def create_node(self, type):
        node = self.node_tree.nodes.new(type=type)
        return NodeWrapper(self, node)

    def link_nodes(self, node_to, in_socket_id, node_from, out_socket_id=''):
        node_from.link_to(node_to, in_socket_id, out_socket_id)

    def delete_node(self, node):
        self.node_tree.nodes.remove(node.node)

    def delete_node_recursive(self, node):
        node.delete_linked()
        self.delete_node(node)

    def prettify(self):
        ''' Formats the placement of material nodes in the shader editor. '''
        margin_x = 100
        margin_y = 50

        def find_output_node():
            for node in self.node_tree.nodes:
                if len(node.outputs) == 0:
                    return node

        def get_node_depths():
            def _traverse(node, graph=OrderedDict(), depth=0):
                node_depth = depth
                if node in graph:
                    current_node_depth = graph[node]
                    node_depth = depth if current_node_depth < depth else current_node_depth
                graph[node] = node_depth
                for input in node.inputs:
                    for link in input.links:
                        _traverse(link.from_node, graph, depth=depth+1)
                return graph

            output_node = find_output_node()
            graph = _traverse(output_node)
            depths = []
            for node, depth in graph.items():
                while len(depths) <= depth:
                    depths.append([])
                depths[depth].append(node)
            return depths

        def get_approximate_node_dimension(node):
            ''' Get an approximation of a node's dimensions.
            Nodes have dimensions attributes, however they are not updated until they are
            displayed in the editor. Therefore, we cannot use them in this case as we create
            and format the entire node tree in a script.
            We use the default node width. The height is infered using the number of inputs 
            and outputs plus the header times a standard height of 24 units as an approximation.
            This does not account for custom node properties.
            '''
            # Hardcoded constant width
            width = node.bl_width_default
            height = 24 * (len(node.inputs) + len(node.outputs) + 1)
            return (width, height)

        node_depths = get_node_depths()
        tree_depth = len(node_depths)

        # 2D bbox, [min_x, min_y, max_x, max_y]
        tree_bbox = [0.0, 0.0, 0.0, 0.0]
        def expand_bbox(tree_bbox, other_bbox):
            if other_bbox[0] < tree_bbox[0]:
                tree_bbox[0] = other_bbox[0]
            if other_bbox[1] < tree_bbox[1]:
                tree_bbox[1] = other_bbox[1]
            if other_bbox[2] > tree_bbox[2]:
                tree_bbox[2] = other_bbox[2]
            if other_bbox[3] > tree_bbox[3]:
                tree_bbox[3] = other_bbox[3]
            return tree_bbox

        current_x = 0.0
        for depth in range(tree_depth):
            depth_width = 0.0
            depth_height = 0.0
            node_dims = []
            for node in node_depths[depth]:
                node_width, node_height = get_approximate_node_dimension(node)
                node_dims.append((node_width, node_height))
                if node_width > depth_width:
                    depth_width = node_width
                depth_height += node_height + margin_y

            current_y = depth_height / 2.0
            for i, node in enumerate(node_depths[depth]):
                node.location = (current_x, current_y)
                node_width, node_height = node_dims[i]
                tree_bbox = expand_bbox(tree_bbox, [current_x, current_y-node_height, current_x+node_width, current_y])
                current_y -= node_height + margin_y

            current_x -= depth_width + margin_x

        center = [(tree_bbox[0]+tree_bbox[2])/2.0, (tree_bbox[1]+tree_bbox[3])/2.0]
        for node in self.node_tree.nodes:
            current_location = node.location
            node.location = (current_location[0]-center[0], current_location[1]-center[1])
