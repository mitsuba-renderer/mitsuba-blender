from .. import logging
from mathutils import Matrix
import numpy as np

from .nodes import next_node_upstream

def convert_world(ctx, world):
    '''
    convert environment lighting. Constant emitter and envmaps are supported

    ctx: the export context
    surface_node: the final node of the shader
    '''
    if world is None:
        logging.info('No Blender world to export.')
        return

    params = {}

    if world.use_nodes and world.node_tree is not None:
        output_node_id = 'World Output'
        if output_node_id not in world.node_tree.nodes:
            logging.warn('Failed to export world: Cannot find world output node.')
            return
        output_node = world.node_tree.nodes[output_node_id]
        if not output_node.inputs["Surface"].is_linked:
            return
        surface_node = next_node_upstream(ctx, output_node.inputs["Surface"])

        if surface_node.type == 'TEX_ENVIRONMENT':
            params = convert_environment_map_emitter(ctx, surface_node)
        else:
            if surface_node.inputs['Strength'].is_linked:
                raise NotImplementedError("Only default emitter strength value is supported.") # TODO: value input
            strength = surface_node.inputs['Strength'].default_value

            if strength == 0: # Don't add an emitter if it emits nothing
                logging.info('Ignoring envmap with zero strength.')
                return

            if surface_node.type in ['BACKGROUND', 'EMISSION']:
                socket = surface_node.inputs["Color"]
                if socket.is_linked:
                    color_node = next_node_upstream(ctx, socket)
                    if color_node.type == 'TEX_ENVIRONMENT':
                        params = convert_environment_map_emitter(ctx, color_node, strength)
                    elif color_node.type == 'RGB':
                        color = color_node.color
                    else:
                        raise NotImplementedError("Node type %s is not supported. Consider using an environment texture or RGB node instead." % color_node.bl_idname)
                else:
                    color = socket.default_value

                if 'type' not in params: # Not an envmap
                    radiance = [x * strength for x in color[:3]]

                    if False: # We want to match Cycles actually!
                        if not ctx.export_default_background and radiance == [0.05087608844041824] * 3:
                            logging.info("Ignoring Blender's default background...")
                            return

                    if np.sum(radiance) == 0:
                        logging.info("Ignoring background emitter with zero emission.")
                        return

                    params = {
                        'type': 'constant',
                        'radiance': ctx.spectrum(radiance)
                    }
            else:
                raise NotImplementedError("Only Background and Emission nodes are supported as final nodes for World export, got '%s'" % surface_node.name)
    else:
        # Single color field for emission, no nodes
        params = {
            'type': 'constant',
            'radiance': ctx.spectrum(world.color)
        }

    return params

def convert_environment_map_emitter(ctx, node, gain=1.0):
    import mitsuba as mi
    params = {
        'type': 'envmap',
        'scale': gain
    }

    key, entry = ctx.export_and_cache_texture(node.image, ctx.directory)
    params[key] = entry

    coordinate_mat = Matrix(((0,0,1,0),(1,0,0,0),(0,1,0,0),(0,0,0,1)))
    to_world = Matrix() #4x4 Identity
    if node.inputs["Vector"].is_linked:
        vector_node = next_node_upstream(ctx, node.inputs["Vector"])
        if vector_node.type != 'MAPPING':
            raise NotImplementedError("Node: %s is not supported. Only a mapping node is supported" % vector_node.bl_idname)
        if not vector_node.inputs["Vector"].is_linked:
            raise NotImplementedError("The node %s should be linked with a Texture coordinate node." % vector_node.bl_idname)
        coord_node = next_node_upstream(ctx, vector_node.inputs["Vector"])
        coord_socket = vector_node.inputs["Vector"].links[0].from_socket
        if coord_node.type != 'TEX_COORD':
            raise NotImplementedError("Unsupported node type: %s." % coord_node.bl_idname)
        if coord_socket.name != 'Generated':
            raise NotImplementedError("Link should come from 'Generated'.")
        #only supported node setup for transform
        if vector_node.vector_type != 'TEXTURE':
            raise NotImplementedError("Only 'Texture' mapping mode is supported.")
        if vector_node.inputs["Location"].is_linked or vector_node.inputs["Rotation"].is_linked or vector_node.inputs["Scale"].is_linked:
            raise NotImplementedError("Transfrom inputs shouldn't be linked.")

        rotation = vector_node.inputs["Rotation"].default_value.to_matrix()
        scale    = vector_node.inputs["Scale"].default_value
        location = vector_node.inputs["Location"].default_value
        for i in range(3):
            for j in range(3):
                to_world[i][j] = rotation[i][j]
            to_world[i][i] *= scale[i]
            to_world[i][3] = location[i]
        to_world = to_world

    # TODO: support other types of mappings (vector, point...)
    # change default position, apply transform and change coordinates

    params['to_world'] = ctx.transform_matrix(to_world @ coordinate_mat)

    return params

def export_world(ctx, world):
    '''
    ctx: export context
    world: blender 'world' object
    '''
    try:
        params = convert_world(ctx, world)
        if params:
            ctx.add_object("World", params, "world")
    except NotImplementedError as err:
        logging.warn("Error while exporting world: %s. Not exporting it." % err.args[0])