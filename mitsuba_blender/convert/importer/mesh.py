'''Convert Mitsuba shapes into Blender meshes.

Mesh-backed shape plugins (ply, obj, serialized, ...) are instantiated by
Mitsuba itself and their vertex buffers are copied into a Blender mesh.
Analytic shapes that are not meshes in Mitsuba (sphere, rectangle, cube,
disk) map to native Blender primitives instead.
'''

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector

from ...io.importer.bl_transform_utils import mi_transform_to_bl_transform


def _set_bl_mesh_shading(bl_mesh, flat_shading=True, flip_normals=False):
    bl_mesh.polygons.foreach_set(
        'use_smooth', [not flat_shading] * len(bl_mesh.polygons))
    if flip_normals:
        bl_mesh.flip_normals()
    bl_mesh.update()


######################
##   Mesh shapes    ##
######################

def _shape_dict(mi_context, mi_props):
    '''Rebuild the loadable dict of a shape from its parsed properties,
    without child objects and without the to_world transform (which becomes
    the Blender object transform instead).'''
    from mitsuba import Properties
    shape_dict = {'type': mi_props.plugin_name()}
    for name, value in mi_props.items():
        if isinstance(value, Properties.ResolvedReference) or name == 'to_world':
            continue
        if name == 'filename':
            resolved = mi_context.resolve_scene_relative_path(value)
            if resolved is None:
                mi_context.log(f'Cannot find the shape file "{value}".',
                               'ERROR')
                return None
            value = resolved
        if isinstance(value, (bool, int, float, str)):
            shape_dict[name] = value
    return shape_dict


def _buffers_to_bl_mesh(name, mi_mesh):
    '''Copy the vertex buffers of a mitsuba.Mesh into a new Blender mesh.'''
    import mitsuba as mi
    params = mi.traverse(mi_mesh)
    vertex_count = mi_mesh.vertex_count()
    face_count = mi_mesh.face_count()

    positions = np.array(params['vertex_positions'], dtype=np.float32)
    faces = np.array(params['faces'], dtype=np.int32)

    bl_mesh = bpy.data.meshes.new(name)
    bl_mesh.vertices.add(vertex_count)
    bl_mesh.vertices.foreach_set('co', positions)
    bl_mesh.loops.add(face_count * 3)
    bl_mesh.loops.foreach_set('vertex_index', faces)
    bl_mesh.polygons.add(face_count)
    bl_mesh.polygons.foreach_set(
        'loop_start', np.arange(0, 3 * face_count, 3, dtype=np.int32))
    bl_mesh.polygons.foreach_set(
        'loop_total', np.full(face_count, 3, dtype=np.int32))
    has_normals = mi_mesh.has_vertex_normals()
    bl_mesh.polygons.foreach_set(
        'use_smooth', np.full(face_count, has_normals, dtype=bool))
    bl_mesh.update(calc_edges=True)
    bl_mesh.validate()

    if has_normals:
        normals = np.array(params['vertex_normals'],
                           dtype=np.float32).reshape(-1, 3)
        bl_mesh.normals_split_custom_set_from_vertices(normals)

    if mi_mesh.has_vertex_texcoords():
        uvs = np.array(params['vertex_texcoords'],
                       dtype=np.float32).reshape(-1, 2)
        uvs[:, 1] = 1.0 - uvs[:, 1]
        uv_layer = bl_mesh.uv_layers.new(name='UVMap')
        # validate() may have deleted invalid faces, so per-loop data
        # cannot be indexed with the pre-validate face buffer
        loop_vertices = np.empty(len(bl_mesh.loops), dtype=np.int32)
        bl_mesh.loops.foreach_get('vertex_index', loop_vertices)
        uv_layer.uv.foreach_set('vector', uvs[loop_vertices].ravel())

    # Extra per-vertex attributes (e.g. vertex colors)
    reserved = {'vertex_positions', 'vertex_normals', 'vertex_texcoords'}
    for key in params.keys():
        if not key.startswith('vertex_') or key in reserved:
            continue
        values = np.array(params[key], dtype=np.float32).ravel()
        dim = values.size // vertex_count
        attr_name = key[len('vertex_'):]
        if dim == 3:
            attr = bl_mesh.color_attributes.new(attr_name, 'FLOAT_COLOR',
                                                'POINT')
            rgba = np.ones((vertex_count, 4), dtype=np.float32)
            rgba[:, :3] = values.reshape(-1, 3)
            attr.data.foreach_set('color', rgba.ravel())
        elif dim == 1:
            attr = bl_mesh.attributes.new(attr_name, 'FLOAT', 'POINT')
            attr.data.foreach_set('value', values)

    return bl_mesh


def mi_mesh_to_bl_shape(mi_context, mi_shape):
    import mitsuba as mi
    shape_dict = _shape_dict(mi_context, mi_shape)
    if shape_dict is None:
        return None
    try:
        mi_mesh = mi.load_dict(shape_dict)
    except Exception as e:
        mi_context.log(f'Cannot load shape "{mi_shape.id()}": {e}', 'ERROR')
        return None
    if not isinstance(mi_mesh, mi.Mesh):
        mi_context.log(f'Mitsuba shape type "{mi_shape.plugin_name()}" is '
                       'not a mesh.', 'ERROR')
        return None

    bl_mesh = _buffers_to_bl_mesh(mi_shape.id(), mi_mesh)
    world_matrix = mi_transform_to_bl_transform(mi_shape.get('to_world', None))
    return bl_mesh, mi_context.mi_space_to_bl_space(world_matrix)


######################
## Analytic shapes  ##
######################

def mi_sphere_to_bl_shape(mi_context, mi_shape):
    import math
    bl_mesh = bpy.data.meshes.new(mi_shape.id())
    bl_bmesh = bmesh.new()

    # Mitsuba composes to_world with the center/radius parameters
    to_world = mi_transform_to_bl_transform(mi_shape.get('to_world', None))
    center = Vector(list(mi_shape.get('center', [0.0, 0.0, 0.0])))
    radius = mi_shape.get('radius', 1.0)
    world_matrix = mi_context.mi_space_to_bl_space(
        to_world @ Matrix.Translation(center))

    # calc_uvs produces no UV layer  therefore the calc_uvs=True is useless
    bmesh.ops.create_uvsphere(bl_bmesh, u_segments=32, v_segments=16,
                              radius=radius)

    # edit UVs on the BMESH, before to_mesh
    uv_layer = bl_bmesh.loops.layers.uv.verify() # get existing or create
    for face in bl_bmesh.faces:
        for loop in face.loops:
            co = loop.vert.co.normalized()
            # In order to match how sphere.cpp does it
            phi = math.atan2(co.y, co.x)
            if phi < 0:
                phi += 2 * math.pi
            u = phi / (2 * math.pi)
            v = 0.5 - math.asin(co.z) / math.pi
            loop[uv_layer].uv = (u, v)

    bl_bmesh.to_mesh(bl_mesh)
    bl_bmesh.free()

    _set_bl_mesh_shading(bl_mesh, flat_shading=False,
                         flip_normals=mi_shape.get('flip_normals', False))

    return bl_mesh, world_matrix


# Analytic shapes that differ only in the bmesh primitive they create.
# The operators are looked up by name at call time: BMeshOpFunc objects
# must not outlive the bmesh.ops attribute access that created them.
_analytic_ops = {
    'disk': ('create_circle',
             dict(cap_ends=True, cap_tris=True, segments=32, radius=1.0)),
    'rectangle': ('create_grid',
                  dict(x_segments=1, y_segments=1, size=1.0)),
    'cube': ('create_cube', dict(size=2.0)),
    #TODO: create a new mapping for other shape
}


def _analytic_to_bl_shape(mi_context, mi_shape):
    op_name, kwargs = _analytic_ops[mi_shape.plugin_name()]
    op = getattr(bmesh.ops, op_name)
    bl_mesh = bpy.data.meshes.new(mi_shape.id())
    bl_bmesh = bmesh.new()

    # bmesh's calc_uvs produces no UV layer for create_grid, create_circle or
    # create_cube (measured), so UVs must be built explicitly. Only rectangle
    # is handled here. Its parameterization is a planar XY projection of
    # [-1,1] onto [0,1]. disk (polar) and cube (per-face) still import without
    # UVs; their Mitsuba parameterizations need to be matched the way mi_sphere_to_bl_shape
    #matches sphere.cpp.
    op(bl_bmesh, **kwargs)
    if mi_shape.plugin_name() == "rectangle":
        uv_layer = bl_bmesh.loops.layers.uv.verify() # get existing or create
        for face in bl_bmesh.faces:
            for loop in face.loops:
                co = loop.vert.co
                loop[uv_layer].uv = ((co.x + 1) / 2, (co.y + 1) / 2)

    #TODO: create the uv mapping for other shapes
    bl_bmesh.to_mesh(bl_mesh)
    bl_bmesh.free()

    _set_bl_mesh_shading(bl_mesh,
                         flip_normals=mi_shape.get('flip_normals', False))

    world_matrix = mi_transform_to_bl_transform(mi_shape.get('to_world', None))
    return bl_mesh, mi_context.mi_space_to_bl_space(world_matrix)


######################
##   Main import    ##
######################

_analytic_converters = {
    'sphere': mi_sphere_to_bl_shape,
    **{name: _analytic_to_bl_shape for name in _analytic_ops},
}


def mi_shape_to_bl_shape(mi_context, mi_shape):
    converter = _analytic_converters.get(mi_shape.plugin_name(),
                                         mi_mesh_to_bl_shape)
    return converter(mi_context, mi_shape)
