from collections import OrderedDict

from mathutils import Color

def rgb_to_rgba(color):
    return color + [1.0]

def rgba_to_rgb(color):
    return Color(color[0], color[1], color[2])

class NodeShaderWrapper:
    ''' Utility wrapper around a node-based Blender shader '''
    def __init__(self, bl_node_tree, init_empty=False, out_node=None):
        ''' Construct a new NodeShaderWrapper
        
        Params
        ------
        bl_node_tree : The wrapped Blender shader node tree
        init_empty : bool, optional
            If set, the material's node tree will be cleared
        out_node : optional
            Reference to the output (root) node of the material.
            If not set, the default output material node is used.
            If init_empty is set, this argument is ignored.
        '''
        self.tree = bl_node_tree
        # Clear the node tree if requested
        if init_empty:
            for node in self.tree.nodes:
                self.tree.nodes.remove(node)
            # Get the output node
            self.out_node = self._ensure_out_node()
        elif out_node is not None:
            # Try to find the provided output node in the node tree
            for node in self.tree.nodes:
                if node == out_node:
                    self.out_node = node
            assert self.out_node is not None
        else:
            # Ensure that an output node exists
            self.out_node = self._ensure_out_node()
        
    def _delete_node_recursive(self, node):
        for input in node.inputs:
            if input.is_linked:
                for link in input.links:
                    self._delete_node_recursive(link.from_node)
        self.tree.nodes.remove(node)

    def _ensure_out_node(self):
        raise NotImplementedError('To implement in subclasses')

    def _get_socket_with_id(self, socket_list, identifier: str):
        for socket in socket_list:
            if socket.identifier == identifier:
                return socket
        return None

    def ensure_node_type(self, path: list[str], bl_idname: str, output_socket_id: str):
        ''' Ensures that a node of a certain type exists at the correct location 
        in the graph. If another node already exists at that location, then it is
        removed.

        Params
        ------
        path: list[str]
            Path to the requested node. Each element of this list represent the identifier
            of the input socket to follow starting from the output node.
        bl_idname: str
            Type of the node that should be connected to the last input in the path.
        output_socket_id: str
            Socket identifier of the newly created node that should be connected to the rest
            of the path.

        Returns
        -------
        The reference to the existing or newly created node.
        '''
        current_node = self.out_node
        next_socket = None
        final_node = None
        for i, next_id in enumerate(path):
            # Ensure that a starting point for the path exists from the current node
            next_socket = self._get_socket_with_id(current_node.inputs, next_id)
            assert next_socket is not None
            if i < len(path)-1:
                # If this is not the last element of the path, follow the path if it exists
                assert next_socket.is_linked
                current_node = next_socket.links[0].from_node
            elif next_socket.is_linked:
                # If this is the last element of the path, check that the last node is of the
                # correct type. If not, delete it recursively.
                final_node = next_socket.links[0].from_node
                if final_node.bl_idname != bl_idname:
                    self._delete_node_recursive(final_node)
                    final_node = None
        # Create the new node only if it was not already present
        if final_node is None:
            final_node = self.tree.nodes.new(type=bl_idname)
            output_socket = self._get_socket_with_id(final_node.outputs, output_socket_id)
            assert output_socket is not None
            self.tree.links.new(output_socket, next_socket)
        return final_node

    def _get_node_depths(self):
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

        graph = _traverse(self.out_node)
        depths = []
        for node, depth in graph.items():
            while len(depths) <= depth:
                depths.append([])
            depths[depth].append(node)
        return depths

    def _get_approximate_node_dimension(self, node):
        ''' Get an approximation of a node's dimensions.
        Nodes have dimensions attributes, however they are not updated until they are
        displayed in the editor. Therefore, we cannot use them in this case as we create
        and format the entire node tree in a script.
        We use the number of inputs and outputs plus the header times a standard height 
        of 24 units as an approximation. POUET
        '''
        # Hardcoded constant width
        width = 240
        height = 24 * (len(node.inputs) + len(node.outputs) + 1)
        return (width, height)

    def format_node_tree(self):
        ''' Formats the placement of material nodes in the shader editor. '''
        margin_x = 100
        margin_y = 50

        node_depths = self._get_node_depths()
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
                node_width, node_height = self._get_approximate_node_dimension(node)
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
        for node in self.tree.nodes:
            current_location = node.location
            node.location = (current_location[0]-center[0], current_location[1]-center[1])

class NodeMaterialWrapper(NodeShaderWrapper):
    ''' Utility wrapper around a node-based Blender material '''
    def __init__(self, bl_mat, init_empty=False, out_node=None):
        ''' Construct a new NodeMaterialWrapper
        
        Params
        ------
        bl_mat : The wrapped Blender material
        init_empty : bool, optional
            If set, the material's node tree will be cleared
        out_node : optional
            Reference to the output (root) node of the material.
            If not set, the default output material node is used.
            If init_empty is set, this argument is ignored.
        '''
        self.bl_mat = bl_mat
        if not bl_mat.use_nodes:
            bl_mat.use_nodes = True
        super(NodeMaterialWrapper, self).__init__(bl_mat.node_tree, init_empty, out_node)

    def _ensure_out_node(self):
        out_node = None
        for node in self.tree.nodes:
            if node.bl_idname == 'ShaderNodeOutputMaterial':
                out_node = node
                break
        if out_node is None:
            out_node = self.tree.nodes.new(type='ShaderNodeOutputMaterial')
        return out_node

class NodeWorldWrapper(NodeShaderWrapper):
    ''' Utility wrapper around a node-based Blender world '''
    def __init__(self, bl_world, init_empty=False, out_node=None):
        ''' Construct a new NodeWorldWrapper
        
        Params
        ------
        bl_world : The wrapped Blender world
        init_empty : bool, optional
            If set, the material's node tree will be cleared
        out_node : optional
            Reference to the output (root) node of the material.
            If not set, the default output material node is used.
            If init_empty is set, this argument is ignored.
        '''
        self.bl_world = bl_world
        if not bl_world.use_nodes:
            bl_world.use_nodes = True
        super(NodeWorldWrapper, self).__init__(bl_world.node_tree, init_empty, out_node)

    def _ensure_out_node(self):
        out_node = None
        for node in self.tree.nodes:
            if node.bl_idname == 'ShaderNodeOutputWorld':
                out_node = node
                break
        if out_node is None:
            out_node = self.tree.nodes.new(type='ShaderNodeOutputWorld')
        return out_node
