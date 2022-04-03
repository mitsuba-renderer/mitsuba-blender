from collections import OrderedDict

from mathutils import Color

def rgb_to_rgba(color):
    return color + [1.0]

def rgba_to_rgb(color):
    return Color(color[0], color[1], color[2])

class NodeMaterialWrapper:
    ''' Utility wrapper around a node-based Blender material '''
    def __init__(self, bl_mat, clear_node_tree=True):
        ''' Construct a new NodeMaterialWrapper
        
        Params
        ------
        bl_mat : The wrapped Blender material
        clear_node_tree : bool, optional
            If set, the material's node tree will be cleared
        '''
        self.bl_mat = bl_mat
        if not bl_mat.use_nodes:
            bl_mat.use_nodes = True
        self.tree = bl_mat.node_tree
        # Clear the node tree if requested
        if clear_node_tree:
            for node in self.tree.nodes:
                self.tree.nodes.remove(node)
        # Get the output node
        self.out_node = self._ensure_out_node()
        
    def _delete_node_recursive(self, node):
        for input in node.inputs:
            if input.is_linked:
                for link in input.links:
                    self._delete_node_recursive(link.from_node)
        self.tree.nodes.remove(node)

    def _ensure_out_node(self):
        out_node = None
        for node in self.tree.nodes:
            if node.bl_idname == 'ShaderNodeOutputMaterial':
                out_node = node
                break
        if out_node is None:
            out_node = self.tree.nodes.new(type='ShaderNodeOutputMaterial')
        return out_node

    def ensure_node_type(self, path, type, output):
        ''' Ensures that a node of a certain type exists at the correct location 
        in the graph. If another node already exists at that location, then it is
        removed.

        Params
        ------
        path: list(str)
            Path to the requested node. Each element of this list represent the name
            of the input to follow starting from the output node.
        type: str
            Type of the node that should be connected to the last input in the path.
        output: str
            Socket name of the newly created node that should be connected to the rest
            of the path.

        Returns
        -------
        The reference to the existing or newly created node.
        '''
        current_node = self.out_node
        next_socket = None
        for i, next in enumerate(path):
            assert next in current_node.inputs
            next_socket = current_node.inputs[next]
            if i < len(path)-1:
                assert next_socket.is_linked
                current_node = next_socket.links[0].from_node
            elif next_socket.is_linked:
                final_node = next_socket.links[0].from_node
                if final_node.bl_idname != type:
                    self._delete_node_recursive(final_node)
        new_node = self.tree.nodes.new(type=type)
        self.tree.links.new(new_node.outputs[output], next_socket)
        return new_node

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


    def format_node_tree(self):
        ''' Formats the placement of material nodes in the shader editor. '''
        margin_x = 100
        margin_y = 20
        # NOTE: The header height is not included when computing the node height
        #       with `node.height`.
        header_height = 20
        max_node_width = 240

        node_depths = self._get_node_depths()
        tree_depth = len(node_depths)
        tree_width = tree_depth * (max_node_width + margin_x) - margin_x

        current_x = 0
        for depth in range(tree_depth):
            current_y = 0
            for node in node_depths[depth]:
                node.location = (current_x, current_y)
                # FIXME: The node `height` attribute does not seem to report the
                #        height when the node tree is not currently displayed ?
                current_y += node.height + header_height + margin_y
            current_x -= max_node_width + margin_x

        for node in self.tree.nodes:
            node.location[0] = node.location[0] - max_node_width + tree_width/2
