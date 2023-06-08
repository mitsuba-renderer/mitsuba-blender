import os
import bpy

from .materials import export_material
from .export_context import Files


def convert_mesh(export_ctx, b_mesh, matrix_world, name, mat_nr):
    '''
    This method creates a mitsuba mesh from a blender mesh and returns it.
    It constructs a dictionary containing the necessary info such as
    pointers to blender's data strucures and then loads the BlenderMesh
    plugin via load_dict.

    Params
    ------
    export_ctx:   The export context.
    b_mesh:       The blender mesh to export.
    matrix_world: The mesh's transform matrix.
    name:         The name to give to the mesh. It will not be saved, so this is mostly
                  for logging/debug purposes.
    mat_nr:       The material ID to export.
    '''
    from mitsuba import load_dict, Point3i
    props = {
        'type': 'blender',
        'version': ".".join(map(str,bpy.app.version))
    }
    b_mesh.calc_normals()
    # Compute the triangle tesselation
    b_mesh.calc_loop_triangles()

    props['name'] = name
    loop_tri_count = len(b_mesh.loop_triangles)
    if loop_tri_count == 0:
        export_ctx.log(f"Mesh: {name} has no faces. Skipping.", 'WARN')
        return
    props['loop_tri_count'] = loop_tri_count

    if len(b_mesh.uv_layers) > 1:
        export_ctx.log(f"Mesh: '{name}' has multiple UV layers. Mitsuba only supports one. Exporting the one set active for render.", 'WARN')
    for uv_layer in b_mesh.uv_layers:
        if uv_layer.active_render: # If there is only 1 UV layer, it is always active
            if uv_layer.name in b_mesh.attributes:
                props['uvs'] = b_mesh.attributes[uv_layer.name].data[0].as_pointer()
            else:
                props['uvs'] = uv_layer.data[0].as_pointer()
            break

    for color_layer in b_mesh.vertex_colors:
        if color_layer.name in b_mesh.attributes:
            props[f'vertex_{color_layer.name}'] = b_mesh.attributes[color_layer.name].data[0].as_pointer()
        else:
            props[f'vertex_{color_layer.name}'] = color_layer.data[0].as_pointer()

    props['loop_tris'] = b_mesh.loop_triangles[0].as_pointer()
    props['loops'] = b_mesh.loops[0].as_pointer()
    props['polys'] = b_mesh.polygons[0].as_pointer()
    if 'position' in b_mesh.attributes:
        props['verts'] = b_mesh.attributes['position'].data[0].as_pointer()
    else:
        props['verts'] = b_mesh.vertices[0].as_pointer()

    if bpy.app.version > (3, 0, 0):
        props['normals'] = b_mesh.vertex_normals[0].as_pointer()
    props['vert_count'] = len(b_mesh.vertices)
    # Apply coordinate change
    if matrix_world:
        props['to_world'] = export_ctx.transform_matrix(matrix_world)

    # material index to export, as only a single material per mesh is suported in mitsuba
    props['mat_nr'] = mat_nr
    if 'material_index' in b_mesh.attributes:
        props['mat_indices'] = b_mesh.attributes['material_index'].data[0].as_pointer()
    else:
        props['mat_indices'] = 0

    # Return the mitsuba mesh
    return load_dict(props)


def export_object(deg_instance, export_ctx, is_particle):
    """
    Convert a blender object to mitsuba and save it as Binary PLY
    """

    b_object = deg_instance.object
    # Remove spurious characters such as slashes
    name_clean = bpy.path.clean_name(b_object.name_full)
    object_id = f"mesh-{name_clean}"

    is_instance_emitter = b_object.parent is not None and b_object.parent.is_instancer
    is_instance = deg_instance.is_instance

    # Only write to file objects that have never been exported before
    if export_ctx.data_get(object_id) is None:
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
            converted_parts.append((
                name_clean,
                -1,
                convert_mesh(export_ctx, b_mesh, transform, name_clean, 0)
            ))
        else:
            refs_per_mat = {}
            for mat_nr in range(mat_count):
                mat = b_mesh.materials[mat_nr]
                if not mat:
                    continue

                # Ensures that the exported mesh parts have unique names,
                # even if multiple material slots refer to the same material.
                n_mat_refs = refs_per_mat.get(mat.name, 0)
                name = f'{name_clean}-{mat.name}'

                if n_mat_refs >= 1:
                    name += f'-{n_mat_refs:03d}'

                mts_mesh = convert_mesh(export_ctx,
                                        b_mesh,
                                        transform,
                                        name,
                                        mat_nr)
                if mts_mesh is not None and mts_mesh.face_count() > 0:
                    converted_parts.append((name, mat_nr, mts_mesh))
                    refs_per_mat[mat.name] = n_mat_refs + 1

                    if n_mat_refs == 0:
                        # Only export this material once
                        export_material(export_ctx, mat)

        if b_object.type != 'MESH':
            b_object.to_mesh_clear()

        # Use a ShapeGroup for instances and split meshes
        use_shapegroup = is_instance or is_instance_emitter or is_particle
        # TODO: Check if shapegroups for split meshes is worth it
        if use_shapegroup:
            group = {
                'type': 'shapegroup'
            }

        for (name, mat_nr, mts_mesh) in converted_parts:
            name = name_clean if len(converted_parts) == 1 else name
            mesh_id = f"mesh-{name}"

            # Save as binary ply
            mesh_folder = os.path.join(export_ctx.directory, export_ctx.subfolders['shape'])
            if not os.path.isdir(mesh_folder):
                os.makedirs(mesh_folder)
            filepath = os.path.join(mesh_folder,  f"{name}.ply")
            mts_mesh.write_ply(filepath)

            # Build dictionary entry
            params = {
                'type': 'ply',
                'filename': f"{export_ctx.subfolders['shape']}/{name}.ply"
            }

            # Add flat shading flag if needed
            if not mts_mesh.has_vertex_normals():
                params["face_normals"] = True

            # Add material info
            if mat_nr == -1:
                if not export_ctx.data_get('default-bsdf'): # We only need to add it once
                    default_bsdf = {
                        'type': 'twosided',
                        'id': 'default-bsdf',
                        'bsdf': {'type':'diffuse'}
                    }
                    export_ctx.data_add(default_bsdf)
                params['bsdf'] = {'type':'ref', 'id':'default-bsdf'}
            else:
                mat_id = f"mat-{b_object.data.materials[mat_nr].name}"
                if export_ctx.exported_mats.has_mat(mat_id): # Add one emitter *and* one bsdf
                    mixed_mat = export_ctx.exported_mats.mats[mat_id]
                    params['bsdf'] = {'type':'ref', 'id':mixed_mat['bsdf']}
                    params['emitter'] = mixed_mat['emitter']
                else:
                    params['bsdf'] = {'type':'ref', 'id':mat_id}

            # Add dict to the scene dict
            if use_shapegroup:
                group[name] = params
            else:
                if export_ctx.export_ids:
                    export_ctx.data_add(params, name=mesh_id)
                else:
                    export_ctx.data_add(params)

        if use_shapegroup:
            export_ctx.data_add(group, name=object_id)

    if is_instance or is_particle:
        params = {
            'type': 'instance',
            'shape': {
                'type': 'ref',
                'id': object_id
            },
            'to_world': export_ctx.transform_matrix(deg_instance.matrix_world)
        }
        export_ctx.data_add(params)
