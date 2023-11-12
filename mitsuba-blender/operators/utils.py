import bpy

def show_mitsuba_node_tree(context, node_tree):
    for area in context.screen.areas:
        if area.type == 'NODE_EDITOR':
            for space in area.spaces:
                if space.type == 'NODE_EDITOR' and not space.pin:
                    space.tree_type = node_tree.bl_idname
                    space.node_tree = node_tree
                    return True
    return False

def init_mitsuba_material_node_tree(node_tree):
    nodes = node_tree.nodes

    output = nodes.new("MitsubaNodeOutputMaterial")
    output.location = 300, 200
    output.select = False

    diffuse = nodes.new("MitsubaNodeDiffuseBSDF")
    diffuse.location = 50, 200

    node_tree.links.new(diffuse.outputs[0], output.inputs[0])
