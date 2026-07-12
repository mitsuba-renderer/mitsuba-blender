'''Blender version compatibility layer.

This is the only module allowed to inspect bpy.app.version. Whenever a
Blender release renames an API that the addon uses, the branch belongs
here, with a fallback for the oldest supported release (4.2 LTS).
'''


def uses_nodes(data):
    '''Whether a material or world shades with its node tree. use_nodes is
    deprecated in Blender 5.0 (reads are always True, writes do nothing)
    and slated for removal in 6.0, where node trees are always present.'''
    return getattr(data, 'use_nodes', True) and data.node_tree is not None


def ensure_node_tree(data):
    '''Enable node-based shading on a material or world and return its
    node tree.'''
    if hasattr(data, 'use_nodes'):
        data.use_nodes = True
    return data.node_tree
