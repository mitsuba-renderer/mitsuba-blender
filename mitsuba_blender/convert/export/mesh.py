'''Convert evaluated Blender meshes into Mitsuba meshes.

The conversion reads the triangulated geometry into numpy arrays and builds
`mitsuba.Mesh` objects directly. When rendering inside Blender, the meshes are
kept in memory and inserted into the scene dict as instantiated objects. When
exporting to a file, they are saved as binary PLY next to the XML and
referenced by filename.
'''

import os
from contextlib import contextmanager

import bpy
import numpy as np

from . import sanitize_attribute_name
from .. import saved_file_resolver


@contextmanager
def resolver_append(directory):
    '''Temporarily add a directory to Mitsuba's file resolver.'''
    with saved_file_resolver() as fr:
        fr.prepend(directory)
        yield


class MeshData:
    '''Numpy snapshot of an evaluated Blender mesh, in Mitsuba conventions.'''

    def __init__(self, export_ctx, b_mesh, name):
        b_mesh.calc_loop_triangles()
        self.tri_count = len(b_mesh.loop_triangles)
        if self.tri_count == 0:
            export_ctx.log(f'Mesh "{name}" has no faces. Skipping.', 'WARN')
            return
        loop_count = len(b_mesh.loops)

        self.tri_loops = np.empty(self.tri_count * 3, dtype=np.int32)
        b_mesh.loop_triangles.foreach_get('loops', self.tri_loops)
        self.tri_loops = self.tri_loops.reshape(-1, 3)

        self.tri_mats = np.empty(self.tri_count, dtype=np.int32)
        b_mesh.loop_triangles.foreach_get('material_index', self.tri_mats)
        # Out-of-range indices (deleted slots, imported data) would match
        # no material slot and silently drop the faces; Blender clamps
        # them when rendering, so do the same
        np.clip(self.tri_mats, 0, max(len(b_mesh.materials) - 1, 0),
                out=self.tri_mats)

        self.loop_vert = np.empty(loop_count, dtype=np.int32)
        b_mesh.loops.foreach_get('vertex_index', self.loop_vert)

        self.positions = np.empty(len(b_mesh.vertices) * 3, dtype=np.float32)
        b_mesh.vertices.foreach_get('co', self.positions)
        self.positions = self.positions.reshape(-1, 3).astype(np.float64)

        # Per-corner normals include the effect of smooth/sharp faces and
        # custom split normals.
        normals = np.empty(loop_count * 3, dtype=np.float32)
        b_mesh.corner_normals.foreach_get('vector', normals)
        self.normals = normals.reshape(-1, 3).astype(np.float64)

        self.uvs = None
        if len(b_mesh.uv_layers) > 1:
            export_ctx.log(f'Mesh "{name}" has multiple UV layers. Mitsuba '
                           'only supports one. Exporting the one set active '
                           'for render.', 'WARN')
        for uv_layer in b_mesh.uv_layers:
            if uv_layer.active_render:
                uvs = np.empty(loop_count * 2, dtype=np.float32)
                uv_layer.uv.foreach_get('vector', uvs)
                self.uvs = uvs.reshape(-1, 2).astype(np.float64)
                self.uvs[:, 1] = 1.0 - self.uvs[:, 1]
                break

        # Color attributes, converted to one RGB value per corner
        self.colors = []
        for attr in b_mesh.color_attributes:
            values = np.empty(len(attr.data) * 4, dtype=np.float32)
            attr.data.foreach_get('color', values)
            values = values.reshape(-1, 4)[:, :3].astype(np.float64)
            if attr.domain == 'POINT':
                values = values[self.loop_vert]
            self.colors.append((sanitize_attribute_name(attr.name), values))


def make_mesh(export_ctx, mesh_data, name, tri_mask, matrix_world, props=None):
    '''Build a mitsuba.Mesh from a subset of the triangles of a MeshData.

    Corners that share the same vertex, normal, UV and color values are
    welded into a single Mitsuba vertex. When a world matrix is given, it is
    combined with the axis conversion matrix and baked into the vertex data.
    Returns None if the selection contains no triangles.
    '''
    import mitsuba as mi

    if mesh_data.tri_count == 0:
        return None
    tris = mesh_data.tri_loops if tri_mask is None else mesh_data.tri_loops[tri_mask]
    face_count = len(tris)
    if face_count == 0:
        return None

    corners = tris.ravel()
    columns = [mesh_data.loop_vert[corners, None].astype(np.float64),
               mesh_data.normals[corners]]
    if mesh_data.uvs is not None:
        columns.append(mesh_data.uvs[corners])
    for _, values in mesh_data.colors:
        columns.append(values[corners])

    unique, inverse = np.unique(np.hstack(columns), axis=0, return_inverse=True)
    faces = inverse.astype(np.uint32).reshape(-1, 3)
    positions = mesh_data.positions[unique[:, 0].astype(np.int64)]
    normals = unique[:, 1:4]

    if matrix_world is not None:
        to_world = np.array(export_ctx.axis_mat @ matrix_world, dtype=np.float64)
        positions = positions @ to_world[:3, :3].T + to_world[:3, 3]
        normals = normals @ np.linalg.inv(to_world[:3, :3])
        if np.linalg.det(to_world[:3, :3]) < 0:
            # Mirroring transforms flip the face winding
            faces = faces[:, ::-1]
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-20)

    mi_mesh = mi.Mesh(name, len(unique), face_count,
                      props=props if props is not None else mi.Properties(),
                      has_vertex_normals=True,
                      has_vertex_texcoords=mesh_data.uvs is not None)
    offset = 4
    if mesh_data.uvs is not None:
        offset = 6
    for attr_name, _ in mesh_data.colors:
        mi_mesh.add_attribute(f'vertex_{attr_name}', 3,
                              unique[:, offset:offset + 3].ravel())
        offset += 3

    params = mi.traverse(mi_mesh)
    params['vertex_positions'] = positions.ravel()
    params['vertex_normals'] = normals.ravel()
    if mesh_data.uvs is not None:
        params['vertex_texcoords'] = unique[:, 4:6].ravel()
    params['faces'] = faces.ravel()
    params.update()
    return mi_mesh


DEFAULT_BSDF_ID = 'default-bsdf'
DEFAULT_BSDF = {
    'type': 'twosided',
    'bsdf': {'type': 'diffuse'}
}


def material_refs(export_ctx, b_mat):
    '''Export the material if needed; return (bsdf_id, emitter_dict or None).'''
    from .materials import export_material
    mat_id = f'mat-{b_mat.name}'
    export_material(export_ctx, b_mat)
    mixed = export_ctx.exported_mats.get(mat_id)
    if mixed is not None:
        return mixed['bsdf'], mixed['emitter']
    if export_ctx.data_get(mat_id) is None:
        return default_bsdf_id(export_ctx), None
    return mat_id, None


def default_bsdf_id(export_ctx):
    '''Return the id of the fallback material, adding it to the dict once.'''
    if not export_ctx.render and export_ctx.data_get(DEFAULT_BSDF_ID) is None:
        export_ctx.data_add(dict(DEFAULT_BSDF), name=DEFAULT_BSDF_ID)
    return DEFAULT_BSDF_ID


def instantiate_bsdf(export_ctx, bsdf_id):
    '''Instantiate a BSDF from its exported dict, once per id (render mode).'''
    import mitsuba as mi
    cache = export_ctx.bsdf_objects
    if bsdf_id not in cache:
        if bsdf_id == DEFAULT_BSDF_ID:
            bsdf_dict = DEFAULT_BSDF
        else:
            bsdf_dict = export_ctx.data_get(bsdf_id)
            del export_ctx.scene_data[export_ctx.sanitize(bsdf_id)]
        with resolver_append(export_ctx.directory):
            cache[bsdf_id] = mi.load_dict(bsdf_dict)
    return cache[bsdf_id]


def shape_props(export_ctx, bsdf_id, emitter_dict):
    '''Build the constructor properties of a shape (render mode).'''
    import mitsuba as mi
    props = mi.Properties()
    props['bsdf'] = instantiate_bsdf(export_ctx, bsdf_id)
    if emitter_dict is not None:
        with resolver_append(export_ctx.directory):
            props['emitter'] = mi.load_dict(emitter_dict)
    return props


class GeometryExporter:
    '''Converts each distinct combination of mesh data and materials once.
    Combinations that are rendered multiple times, including depsgraph
    instances from particles and instanced collections, become a shapegroup
    that is referenced by one Mitsuba instance per occurrence.

    The caller iterates the dependency graph twice: a counting pass over all
    mesh-like instances (count_instance), then a conversion pass
    (export_instance). Splitting the work this way avoids keeping evaluated
    object references alive across iteration steps, which Blender forbids.'''

    # Marks combinations that cannot become a shapegroup because a part
    # carries an emitter, which Mitsuba does not allow on group members
    EMITTER_FALLBACK = object()

    def __init__(self, export_ctx):
        self.export_ctx = export_ctx
        self.occurrences = {}
        self.group_ids = {}
        self.fallback_counts = {}

    @staticmethod
    def instance_key(deg_instance):
        b_object = deg_instance.object
        materials = tuple(slot.material.name if slot.material else None
                          for slot in b_object.material_slots)
        return (b_object.data.session_uid, materials)

    @staticmethod
    def is_prototype(deg_instance):
        '''Blender does not render the prototype object of an instancer
        (e.g. the child of a vertex instancer) at its own location.'''
        b_object = deg_instance.object
        return not deg_instance.is_instance and b_object.parent is not None \
            and b_object.parent.original.is_instancer

    def count_instance(self, deg_instance):
        key = self.instance_key(deg_instance)
        count = self.occurrences.get(key, 0)
        if not self.is_prototype(deg_instance):
            count += 1
        self.occurrences[key] = count

    def export_instance(self, deg_instance):
        count = self.occurrences[self.instance_key(deg_instance)]
        if count == 0:
            return
        if count == 1:
            # Rendered exactly once: a plain shape with the transform baked in
            if not self.is_prototype(deg_instance):
                self.export_single(deg_instance)
        else:
            self.export_instanced(deg_instance)

    def export_single(self, deg_instance):
        key = self.instance_key(deg_instance)
        if key in self.group_ids:
            return
        self.group_ids[key] = None
        name_clean = bpy.path.clean_name(deg_instance.object.name_full)
        self.export_plain(deg_instance, name_clean)

    def export_plain(self, deg_instance, name_clean):
        '''Export one occurrence as plain shapes with the transform baked
        into the vertex data.'''
        export_ctx = self.export_ctx
        converted = self.convert_parts(deg_instance.object, name_clean,
                                       deg_instance.matrix_world)
        for name, bsdf_id, emitter, mi_mesh in converted:
            name = name_clean if len(converted) == 1 else name
            entry = self.make_entry(name, bsdf_id, emitter, mi_mesh)
            if export_ctx.render or export_ctx.export_ids:
                export_ctx.data_add(entry, name=f'mesh-{name}')
            else:
                export_ctx.data_add(entry)

    def uses_emitter(self, b_object):
        '''Whether any material of the object exports an emitter.'''
        for slot in b_object.material_slots:
            if slot.material is not None and \
                    material_refs(self.export_ctx, slot.material)[1] is not None:
                return True
        return False

    def export_instanced(self, deg_instance):
        export_ctx = self.export_ctx
        key = self.instance_key(deg_instance)
        if key not in self.group_ids:
            self.group_ids[key] = None
            b_object = deg_instance.object
            name_clean = bpy.path.clean_name(b_object.name_full)
            if self.uses_emitter(b_object):
                export_ctx.log(
                    f'Object "{b_object.name_full}" occurs multiple times '
                    'and has an emissive material, which Mitsuba does not '
                    'support on instanced shapes. Exporting each occurrence '
                    'as a separate shape.', 'WARN')
                self.group_ids[key] = self.EMITTER_FALLBACK
            else:
                converted = self.convert_parts(b_object, name_clean, None)
                group = {'type': 'shapegroup'}
                for name, bsdf_id, emitter, mi_mesh in converted:
                    name = name_clean if len(converted) == 1 else name
                    group[export_ctx.sanitize(name)] = \
                        self.make_entry(name, bsdf_id, emitter, mi_mesh)
                if len(group) > 1:
                    object_id = f'mesh-{name_clean}'
                    export_ctx.data_add(group, name=object_id)
                    self.group_ids[key] = object_id

        object_id = self.group_ids[key]
        if object_id is self.EMITTER_FALLBACK:
            if not self.is_prototype(deg_instance):
                count = self.fallback_counts.get(key, 0)
                self.fallback_counts[key] = count + 1
                name_clean = bpy.path.clean_name(
                    deg_instance.object.name_full)
                self.export_plain(deg_instance, f'{name_clean}-{count:03d}')
            return
        if object_id is not None and not self.is_prototype(deg_instance):
            export_ctx.data_add({
                'type': 'instance',
                'shape': export_ctx.create_ref(object_id),
                'to_world': export_ctx.transform_matrix(
                    deg_instance.matrix_world)
            })

    def convert_parts(self, b_object, name_clean, transform):
        '''Convert the object into one (name, bsdf_id, emitter, mesh) tuple
        per non-empty material slot.'''
        export_ctx = self.export_ctx
        if b_object.type == 'MESH':
            b_mesh = b_object.data
        else: # Metaballs, text, surfaces
            b_mesh = b_object.to_mesh()

        mesh_data = MeshData(export_ctx, b_mesh, name_clean)
        if mesh_data.tri_count == 0:
            if b_object.type != 'MESH':
                b_object.to_mesh_clear()
            return []

        # One entry per material slot: (name, bsdf_id, emitter_dict, tri_mask)
        parts = []
        slots = b_object.material_slots
        if len(slots) == 0:
            parts.append((name_clean, default_bsdf_id(export_ctx), None, None))
        else:
            refs_per_mat = {}
            for mat_nr, slot in enumerate(slots):
                if slot.material is None:
                    # Blender renders faces assigned to an empty slot with
                    # its default material
                    parts.append((f'{name_clean}-slot{mat_nr}',
                                  default_bsdf_id(export_ctx), None,
                                  mesh_data.tri_mats == mat_nr))
                    continue
                # Ensure unique part names even if multiple slots refer to
                # the same material
                n_refs = refs_per_mat.get(slot.material.name, 0)
                refs_per_mat[slot.material.name] = n_refs + 1
                # The part name doubles as a PLY filename, so the material
                # name needs cleaning too
                name = bpy.path.clean_name(
                    f'{name_clean}-{slot.material.name}')
                if n_refs >= 1:
                    name += f'-{n_refs:03d}'
                bsdf_id, emitter = material_refs(export_ctx, slot.material)
                parts.append((name, bsdf_id, emitter,
                              mesh_data.tri_mats == mat_nr))

        converted = []
        for name, bsdf_id, emitter, tri_mask in parts:
            props = shape_props(export_ctx, bsdf_id, emitter) \
                if export_ctx.render else None
            mi_mesh = make_mesh(export_ctx, mesh_data, name, tri_mask,
                                transform, props)
            if mi_mesh is not None:
                converted.append((name, bsdf_id, emitter, mi_mesh))

        if b_object.type != 'MESH':
            b_object.to_mesh_clear()
        return converted

    def make_entry(self, name, bsdf_id, emitter, mi_mesh):
        '''Return the scene dict entry of a converted mesh part.'''
        export_ctx = self.export_ctx
        if export_ctx.render:
            return mi_mesh
        # Save as binary PLY, referenced by a relative path
        mesh_folder = os.path.join(export_ctx.directory,
                                   export_ctx.MESHES_FOLDER)
        os.makedirs(mesh_folder, exist_ok=True)
        mi_mesh.write_ply(os.path.join(mesh_folder, f'{name}.ply'))
        entry = {
            'type': 'ply',
            'filename': f'{export_ctx.MESHES_FOLDER}/{name}.ply',
            'bsdf': export_ctx.create_ref(bsdf_id)
        }
        if emitter is not None:
            entry['emitter'] = emitter
        return entry
