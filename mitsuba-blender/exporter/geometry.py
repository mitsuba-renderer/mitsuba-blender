from mathutils import Matrix
import os
import bpy
import numpy as np

from .. import logging

from .materials import convert_displacement_map

def convert_mesh(ctx, b_mesh, matrix_world, name, mat_nr):
    '''
    This method creates a mitsuba mesh from a blender mesh and returns it.
    It constructs a dictionary containing the necessary info such as
    pointers to blender's data structures and then loads the BlenderMesh
    plugin via load_dict.

    Params
    ------
    ctx:   The export context.
    b_mesh:       The blender mesh to export.
    matrix_world: The mesh's transform matrix.
    name:         The name to give to the mesh. It will not be saved, so this is mostly
                  for logging/debug purposes.
    mat_nr:       The material ID to export.
    '''
    props = {
        'type': 'blender',
        'version': ".".join(map(str, bpy.app.version))
    }

    if bpy.app.version < (4, 0, 0):
        b_mesh.calc_normals()

    # Compute the triangle tesselation
    b_mesh.calc_loop_triangles()

    props['name'] = name

    loop_tri_count = len(b_mesh.loop_triangles)
    if loop_tri_count == 0:
        logging.warn(f"Mesh: {name} has no faces. Skipping.")
        return

    props['loop_tri_count'] = loop_tri_count

    if len(b_mesh.uv_layers) > 1:
        logging.warn(f"Mesh: '{name}' has multiple UV layers. Mitsuba only supports one. Exporting the one set active for render.")

    for uv_layer in b_mesh.uv_layers:
        if uv_layer.active_render: # If there is only 1 UV layer, it is always active
            if uv_layer.name in b_mesh.attributes:
                props['uvs'] = b_mesh.attributes[uv_layer.name].data[0].as_pointer()
            else:
                props['uvs'] = uv_layer.data[0].as_pointer()
            break

    # for color_layer in b_mesh.vertex_colors:
    #     if color_layer.name in b_mesh.attributes:
    #         props[f'vertex_{color_layer.name}'] = b_mesh.attributes[color_layer.name].data[0].as_pointer()
    #     else:
    #         props[f'vertex_{color_layer.name}'] = color_layer.data[0].as_pointer()

    props['loop_tris'] = b_mesh.loop_triangles[0].as_pointer()

    if '.corner_vert' in b_mesh.attributes:
        # Blender 3.6+ layout
        props['loops'] = b_mesh.attributes['.corner_vert'].data[0].as_pointer()
    else:
        props['loops'] = b_mesh.loops[0].as_pointer()

    if 'sharp_face' in b_mesh.attributes:
        props['sharp_face'] = b_mesh.attributes['sharp_face'].data[0].as_pointer()

    if bpy.app.version >= (3, 6, 0):
        props['polys'] = b_mesh.loop_triangle_polygons[0].as_pointer()
    else:
        props['polys'] = b_mesh.polygons[0].as_pointer()

    if 'position' in b_mesh.attributes:
        # Blender 3.5+ layout
        props['verts'] = b_mesh.attributes['position'].data[0].as_pointer()
    else:
        props['verts'] = b_mesh.vertices[0].as_pointer()

    if bpy.app.version > (3, 0, 0):
        props['normals'] = b_mesh.vertex_normals[0].as_pointer()

    props['vert_count'] = len(b_mesh.vertices)

    # Apply coordinate change
    if matrix_world:
        props['to_world'] = ctx.transform_matrix(matrix_world)

    # Material index to export, as only a single material per mesh is suported in mitsuba
    if mat_nr is not None:
        props['mat_nr'] = mat_nr

    if 'material_index' in b_mesh.attributes:
        # Blender 3.4+ layout
        props['mat_indices'] = b_mesh.attributes['material_index'].data[0].as_pointer()
    else:
        props['mat_indices'] = 0

    return props

def export_object(ctx, instance, is_particle):
    '''
    Convert a blender object to mitsuba and save it as Binary PLY
    '''
    b_object = instance.object

    # Remove spurious characters such as slashes
    name_clean = bpy.path.clean_name(b_object.name_full)

    # In Mitsuba `.` are not supported in object's name as it's used in `mi.traverse`
    name_clean = name_clean.replace('.', '_')

    object_id = f"mesh-{name_clean}"

    logging.debug(f'Converting object {object_id}')

    is_instance_emitter = b_object.parent is not None and b_object.parent.is_instancer
    is_instance = instance.is_instance

    # Only write to file objects that have never been exported before
    if not object_id in ctx.scene_dict:
        if b_object.type == 'MESH':
            b_mesh = b_object.data
        else: # Metaballs, text, surfaces
            b_mesh = b_object.to_mesh()

        # Convert the mesh into one mitsuba mesh per different material
        mat_count = len(b_mesh.materials)
        converted_parts = []
        if is_instance or is_instance_emitter:
            transform = None
        else:
            transform = b_object.matrix_world

        if mat_count == 0: # No assigned material
            mesh_dict = convert_mesh(ctx, b_mesh, transform, name_clean, 0)
            converted_parts.append((-1, mesh_dict))

        for mat_nr in range(mat_count):
            material = b_mesh.materials[mat_nr]
            if material:
                mesh_dict = convert_mesh(ctx,
                                         b_mesh,
                                         transform,
                                         f"{name_clean}-{material.name}",
                                         mat_nr)

                if material.displacement_method in ['DISPLACEMENT', 'BOTH']:
                    displacement = convert_displacement_map(ctx, material)
                    if displacement:
                        mesh_dict['displacement'] = displacement

                if mesh_dict is not None:
                    converted_parts.append((mat_nr, mesh_dict))

        if b_object.type != 'MESH':
            b_object.to_mesh_clear()

        part_count = len(converted_parts)

        # Use a ShapeGroup for instances and split meshes
        use_shapegroup = is_instance or is_instance_emitter or is_particle
        # TODO: Check if shapegroups for split meshes is worth it
        if use_shapegroup:
            group = { 'type': 'shapegroup' }

        for (mat_nr, mesh_dict) in converted_parts:
            # Determine the file name
            if part_count == 1:
                name = f"{name_clean}"
            else:
                name = f"{name_clean}-{b_mesh.materials[mat_nr].name}"
            mesh_id = f"mesh-{name}"

            if ctx.export_assets:
                # Save as binary ply
                mesh_folder = os.path.join(ctx.directory, ctx.SUBFOLDERS['shape'])
                os.makedirs(mesh_folder, exist_ok=True)
                filepath = os.path.join(mesh_folder,  f"{name}.ply")

                import mitsuba as mi
                mts_mesh = mi.load_dict(mesh_dict)

                if mts_mesh is None or mts_mesh.face_count() == 0:
                    continue

                mts_mesh.write_ply(filepath)

                # Build dictionary entry
                mesh_dict = {
                    'type': 'ply',
                    'filename': f"{ctx.SUBFOLDERS['shape']}/{name}.ply"
                }

                # Add flat shading flag if needed
                if not mts_mesh.has_vertex_normals():
                    mesh_dict["face_normals"] = True

            # Add material info
            if mat_nr == -1:
                if not 'default-bsdf' in ctx.scene_dict: # We only need to add it once
                    default_bsdf = {
                        'type': 'twosided',
                        'id': 'default-bsdf',
                        'bsdf': { 'type': 'diffuse' }
                    }
                    ctx.add_object('default_bsdf', default_bsdf)
                mesh_dict['bsdf'] = { 'type': 'ref', 'id': 'default-bsdf' }
            else:
                mat_id = ctx.sanatize_id(f'mat-{b_object.data.materials[mat_nr].name}')
                if mat_id in ctx.exported_mats: # Add one emitter *and* one bsdf
                    mixed_mat = ctx.exported_mats[mat_id]
                    mat_id = mixed_mat['bsdf']
                    mesh_dict['emitter'] = mixed_mat['emitter']

                # In Mitsuba `.` are not supported in object's name as it's used in `mi.traverse`
                mat_id = mat_id.replace('.', '_')

                mesh_dict['bsdf'] = { 'type': 'ref', 'id': mat_id }

            # Add dict to the scene dict
            if use_shapegroup:
                group[name] = mesh_dict
            else:
                ctx.add_object(b_object.name_full, mesh_dict, mesh_id)

        if use_shapegroup:
            ctx.add_object(b_object.name_full, group, object_id)

    if is_instance or is_particle:
        mesh_dict = {
            'type': 'instance',
            'shape': {
                'type': 'ref',
                'id': object_id
            },
            'to_world': ctx.transform_matrix(instance.matrix_world)
        }
        ctx.add_object(b_object.name_full, mesh_dict)
