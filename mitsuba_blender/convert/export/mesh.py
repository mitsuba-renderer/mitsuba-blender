'''Convert evaluated Blender meshes into Mitsuba meshes.

The conversion reads the geometry into numpy arrays and builds `mitsuba.Mesh`
objects directly. When rendering inside Blender, the meshes are kept in memory
and inserted into the scene dict as instantiated objects, with the object
transform baked in. When exporting to a file, they are appended to one shared
`.serialized` file next to the XML, and each shape references its sub-mesh by
index and carries its own `to_world`.
'''
import bpy
import numpy as np

from . import sanitize_attribute_name


def read_attribute(b_mesh, name, prop, dtype, size, legacy=None):
    '''Bulk-read one of Blender's generic mesh attributes.

    These memcpy straight out of Blender's contiguous storage. The legacy RNA
    collections expose the same values, but `foreach_get` walks them element
    by element and is orders of magnitude slower, so they only serve as the
    fallback `legacy=(collection, property)` for an attribute that a Blender
    release might rename. Returns None when the attribute is absent and no
    fallback was given.
    '''
    out = np.empty(size, dtype=dtype)
    attr = b_mesh.attributes.get(name)
    if attr is not None:
        attr.data.foreach_get(prop, out)
    elif legacy is not None:
        legacy[0].foreach_get(legacy[1], out)
    else:
        return None
    return out


class MeshData:
    '''Numpy snapshot of an evaluated Blender mesh, in Mitsuba conventions.

    The per-corner data stays in Blender's per-loop layout, with the faces
    indexing into it. Mitsuba reads it through that map, so the export never
    materializes a corner-aligned copy of an attribute. The geometry stays in
    object space: the shapes carry their transform as 'to_world', which
    Mitsuba bakes when the mesh is built or loaded.

    The mesh is described to Mitsuba as polygons, which it fans into
    triangles itself. Reading Blender's own triangulation instead costs
    more than everything else here put together, but handles the concave and
    non-planar faces that a fan does not; `export_ctx.blender_triangulation`
    selects it. Either way `prim_mats` holds one material index per
    primitive, and the primitives are what a material slot selects.
    '''

    def __init__(self, export_ctx, b_mesh, name):
        face_count = len(b_mesh.polygons)
        loop_count = len(b_mesh.loops)
        self.face_offsets = None
        self.tri_loops = None
        # Faces that already are triangles need no triangulation from either
        # side: primitive i then owns the corners 3i..3i+2
        self.all_triangles = loop_count == 3 * face_count

        # Blender's triangulation is only worth its cost for faces that need
        # splitting, and only when the user asked for it
        split_in_blender = export_ctx.blender_triangulation \
            and not self.all_triangles
        if split_in_blender:
            b_mesh.calc_loop_triangles()
            self.prim_count = len(b_mesh.loop_triangles)
        else:
            self.prim_count = face_count
        if self.prim_count == 0:
            export_ctx.log(f'Mesh "{name}" has no faces. Skipping.', 'WARN')
            return

        materials = read_attribute(b_mesh, 'material_index', 'value',
                                   np.int32, face_count)
        if materials is not None:
            # Out-of-range indices (deleted slots, imported data) would match
            # no material slot and silently drop the faces; Blender clamps
            # them when rendering, so do the same
            np.clip(materials, 0, max(len(b_mesh.materials) - 1, 0),
                    out=materials)

        if split_in_blender:
            # The primitives are Blender's triangles, and each one inherits
            # the material of the polygon it was cut from
            tri_loops = np.empty(self.prim_count * 3, dtype=np.int32)
            b_mesh.loop_triangles.foreach_get('loops', tri_loops)
            self.tri_loops = tri_loops.reshape(-1, 3)
            if materials is not None:
                tri_face = np.empty(self.prim_count, dtype=np.int32)
                b_mesh.loop_triangle_polygons.foreach_get('value', tri_face)
                materials = materials[tri_face]
        elif not self.all_triangles:
            # Mitsuba fans the polygons, so hand it their corner ranges
            self.face_offsets = np.empty(face_count + 1, dtype=np.int32)
            b_mesh.polygons.foreach_get('loop_start',
                                        self.face_offsets[:face_count])
            self.face_offsets[face_count] = loop_count

        self.prim_mats = materials if materials is not None \
            else np.zeros(self.prim_count, dtype=np.int32)

        self.loop_vert = read_attribute(
            b_mesh, '.corner_vert', 'value', np.int32, loop_count,
            legacy=(b_mesh.loops, 'vertex_index'))
        self.positions = read_attribute(
            b_mesh, 'position', 'vector', np.float32,
            len(b_mesh.vertices) * 3,
            legacy=(b_mesh.vertices, 'co')).reshape(-1, 3)

        # Per-corner normals include the effect of smooth/sharp faces and
        # custom split normals.
        self.normals = np.empty(loop_count * 3, dtype=np.float32)
        b_mesh.corner_normals.foreach_get('vector', self.normals)
        self.normals = self.normals.reshape(-1, 3)

        self.uvs = None
        if len(b_mesh.uv_layers) > 1:
            export_ctx.log(f'Mesh "{name}" has multiple UV layers. Mitsuba '
                           'only supports one. Exporting the one set active '
                           'for render.', 'WARN')
        for uv_layer in b_mesh.uv_layers:
            if uv_layer.active_render:
                uvs = np.empty(loop_count * 2, dtype=np.float32)
                uv_layer.uv.foreach_get('vector', uvs)
                # Exported verbatim: the differing image row convention is
                # folded into each texture's 'to_uv', and flipping v here
                # would reverse the bitangent of the MikkTSpace frame
                self.uvs = uvs.reshape(-1, 2)
                break

        # Color attributes, converted to one RGB value per loop
        self.colors = []
        for attr in b_mesh.color_attributes:
            values = np.empty(len(attr.data) * 4, dtype=np.float32)
            attr.data.foreach_get('color', values)
            values = np.ascontiguousarray(values.reshape(-1, 4)[:, :3])
            if attr.domain == 'POINT':
                values = values[self.loop_vert]
            self.colors.append((sanitize_attribute_name(attr.name), values))

    def topology(self, prim_mask):
        '''The (corner_index, face_offsets) pair describing the selected
        primitives. Both are None when the corners already march through the
        loops three at a time, which lets Mitsuba read the pools without any
        index array at all.'''
        if self.tri_loops is not None:
            tris = self.tri_loops if prim_mask is None \
                else self.tri_loops[prim_mask]
            return tris.ravel(), None
        if prim_mask is None:
            return None, self.face_offsets

        selected = np.flatnonzero(prim_mask).astype(np.int32)
        if self.all_triangles:
            return (selected[:, None] * 3
                    + np.arange(3, dtype=np.int32)).ravel(), None

        # Concatenate the corner ranges of the selected polygons, rebasing
        # the offsets onto the compacted result
        starts = self.face_offsets[selected]
        counts = self.face_offsets[selected + 1] - starts
        offsets = np.empty(len(selected) + 1, dtype=np.int32)
        offsets[0] = 0
        np.cumsum(counts, out=offsets[1:])
        corners = np.arange(offsets[-1], dtype=np.int32) \
            + np.repeat(starts - offsets[:-1], counts)
        return corners, offsets


def make_mesh(mesh_data, name, prim_mask, props=None):
    '''Build a mitsuba.Mesh from a subset of the primitives of a MeshData.

    Corners that share the same vertex, normal, UV and color values are
    welded into a single Mitsuba vertex. Nothing here copies the per-corner
    data: Blender's per-loop pools are handed over as they are, and the
    topology arrays are None for a mesh whose faces are already triangles,
    which lets Mitsuba read the pools without any index array at all. Any
    'to_world' on `props` is baked by the build itself. Returns None if the
    selection contains no primitives.
    '''
    import mitsuba as mi

    if mesh_data.prim_count == 0:
        return None
    if prim_mask is not None and not prim_mask.any():
        return None
    if props is None:
        props = mi.Properties()

    corners, face_offsets = mesh_data.topology(prim_mask)
    props.set_id(name)
    mesh = mi.Mesh(props)
    mesh.from_corners(
        positions=mesh_data.positions,
        corner_vertex=mesh_data.loop_vert,
        corner_index=corners,
        face_offsets=face_offsets,
        normals=mesh_data.normals,
        texcoords=mesh_data.uvs,
        attrs={f'vertex_{attr_name}': values
               for attr_name, values in mesh_data.colors})
    return mesh


DEFAULT_BSDF_ID = 'default-bsdf'
DEFAULT_BSDF = {
    'type': 'twosided',
    'bsdf': {'type': 'diffuse'}
}
DEFAULT_NULL_BSDF_ID = 'default_null_bsdf'
NULL_BSDF = {
        'type' : 'null'
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
    if export_ctx.data_get(DEFAULT_BSDF_ID) is None:
        export_ctx.data_add(dict(DEFAULT_BSDF), name=DEFAULT_BSDF_ID)
    return DEFAULT_BSDF_ID

def default_null_bsdf_id(export_ctx):
    '''Return the id of the null material, adding it to the dict once.'''
    if export_ctx.data_get(DEFAULT_NULL_BSDF_ID) is None:
        export_ctx.data_add(dict(NULL_BSDF), name=DEFAULT_NULL_BSDF_ID)
    return DEFAULT_NULL_BSDF_ID

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
        '''Export one occurrence as plain shapes carrying their own
        object-to-world transform.'''
        export_ctx = self.export_ctx
        to_world = export_ctx.transform_matrix(deg_instance.matrix_world)
        converted = self.convert_parts(deg_instance.object, name_clean)
        for name, bsdf_id, emitter, mi_mesh in converted:
            entry = self.make_entry(bsdf_id, emitter, mi_mesh, to_world)
            if export_ctx.export_ids:
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
                converted = self.convert_parts(b_object, name_clean)
                group = {'type': 'shapegroup'}
                for name, bsdf_id, emitter, mi_mesh in converted:
                    group[export_ctx.sanitize(name)] = \
                        self.make_entry(bsdf_id, emitter, mi_mesh)
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

    def convert_parts(self, b_object, name_clean):
        '''Convert the object into one (name, bsdf_id, emitter, mesh) tuple
        per non-empty material slot.'''
        export_ctx = self.export_ctx
        if b_object.type == 'MESH':
            b_mesh = b_object.data
        else: # Metaballs, text, surfaces
            b_mesh = b_object.to_mesh()

        mesh_data = MeshData(export_ctx, b_mesh, name_clean)
        if mesh_data.prim_count == 0:
            if b_object.type != 'MESH':
                b_object.to_mesh_clear()

            return []

        # One entry per material slot: (name, bsdf_id, emitter_dict, prim_mask)
        parts = []
        slots = b_object.material_slots
        if len(slots) == 0:
            parts.append((name_clean, default_bsdf_id(export_ctx), None, None))
        else:
            refs_per_mat = {}
            for mat_nr, slot in enumerate(slots):
                prim_mask = mesh_data.prim_mats == mat_nr
                if not prim_mask.any():
                    continue
                if slot.material is None:
                    # Blender renders faces assigned to an empty slot with
                    # its default material
                    parts.append((f'{name_clean}-slot{mat_nr}',
                                  default_bsdf_id(export_ctx), None, prim_mask))
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

                if not b_object.visible_camera:
                    if emitter is not None:
                        emitter['visible'] = False
                    bsdf_id = default_null_bsdf_id(export_ctx)

                parts.append((name, bsdf_id, emitter, prim_mask))

        # The material suffix only serves to tell several parts apart. An
        # object that stays in one piece keeps its own name, and the bsdf
        # reference of the shape already records the material.
        if len(parts) == 1:
            parts[0] = (name_clean, *parts[0][1:])

        converted = [(name, bsdf_id, emitter,
                      make_mesh(mesh_data, name, prim_mask, None))
                     for name, bsdf_id, emitter, prim_mask in parts]

        if b_object.type != 'MESH':
            b_object.to_mesh_clear()
        return converted

    def make_entry(self, bsdf_id, emitter, mi_mesh, to_world=None):
        '''Return the scene dict entry of a converted mesh part.'''
        export_ctx = self.export_ctx
        # Every mesh goes into one shared .serialized file, addressed by the
        # index it was appended at
        entry = {
            'type': 'serialized',
            'filename': export_ctx.serialized_filename(),
            'shape_index': export_ctx.add_serialized_mesh(mi_mesh),
            'bsdf': export_ctx.create_ref(bsdf_id)
        }
        if to_world is not None:
            entry['to_world'] = to_world
        if emitter is not None:
            entry['emitter'] = emitter
        return entry
