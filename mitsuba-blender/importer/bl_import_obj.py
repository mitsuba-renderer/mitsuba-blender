# SPDX-License-Identifier: GPL-2.0-or-later

# <pep8 compliant>

# Script copyright (C) Campbell Barton
# Contributors: Campbell Barton, Jiri Hnidek, Paolo Ciccone

"""
This script is based on the OBJ importer for Blender

http://wiki.blender.org/index.php/Scripts/Manual/Import/wavefront_obj
"""

import array
import os
import bpy

from bpy_extras.io_utils import unpack_list


def line_value(line_split):
    """
    Returns 1 string representing the value for this line
    None will be returned if there's only 1 word
    """
    length = len(line_split)
    if length == 1:
        return None

    elif length == 2:
        return line_split[1]

    elif length > 2:
        return b' '.join(line_split[1:])


def filenames_group_by_ext(line, ext):
    """
    Splits material libraries supporting spaces, so:
    b'foo bar.mtl baz spam.MTL' -> (b'foo bar.mtl', b'baz spam.MTL')
    Also handle " chars (some software use those to protect filenames with spaces, see T67266... sic).
    """
    # Note that we assume that if there are some " in that line,
    # then all filenames are properly enclosed within those...
    start = line.find(b'"') + 1
    if start != 0:
        while start != 0:
            end = line.find(b'"', start)
            if end != -1:
                yield line[start:end]
                start = line.find(b'"', end + 1) + 1
            else:
                break
        return

    line_lower = line.lower()
    i_prev = 0
    while i_prev != -1 and i_prev < len(line):
        i = line_lower.find(ext, i_prev)
        if i != -1:
            i += len(ext)
        yield line[i_prev:i].strip()
        i_prev = i

def face_is_edge(face):
    """Simple check to test whether given (temp, working) data is an edge, and not a real face."""
    face_vert_loc_indices = face[0]
    face_vert_nor_indices = face[1]
    return len(face_vert_nor_indices) == 1 or len(face_vert_loc_indices) == 2


def split_mesh(verts_loc, faces, filepath, split_meshes):
    """
    Takes vert_loc and faces, and separates into multiple sets of
    (verts_loc, faces, dataname)
    """

    filename = os.path.splitext((os.path.basename(filepath)))[0]

    if not split_meshes or not faces:
        use_verts_nor = any(f[1] for f in faces)
        use_verts_tex = any(f[2] for f in faces)
        # use the filename for the object name since we aren't chopping up the mesh.
        return [(verts_loc, faces, filename, use_verts_nor, use_verts_tex)]

    def key_to_name(key):
        # if the key is a tuple, join it to make a string
        if not key:
            return filename  # assume its a string. make sure this is true if the splitting code is changed
        elif isinstance(key, bytes):
            return key.decode('utf-8', 'replace')
        else:
            return "_".join(k.decode('utf-8', 'replace') for k in key)

    # Return a key that makes the faces unique.
    face_split_dict = {}

    oldkey = -1  # initialize to a value that will never match the key

    for face in faces:
        (face_vert_loc_indices,
         face_vert_nor_indices,
         face_vert_tex_indices,
         _,
         context_object_key,
         _,
         ) = face
        key = context_object_key

        if oldkey != key:
            # Check the key has changed.
            (verts_split, faces_split, vert_remap,
             use_verts_nor, use_verts_tex) = face_split_dict.setdefault(key, ([], [], {}, [], []))
            oldkey = key

        if not face_is_edge(face):
            if not use_verts_nor and face_vert_nor_indices:
                use_verts_nor.append(True)

            if not use_verts_tex and face_vert_tex_indices:
                use_verts_tex.append(True)

        # Remap verts to new vert list and add where needed
        for loop_idx, vert_idx in enumerate(face_vert_loc_indices):
            map_index = vert_remap.get(vert_idx)
            if map_index is None:
                map_index = len(verts_split)
                vert_remap[vert_idx] = map_index  # set the new remapped index so we only add once and can reference next time.
                verts_split.append(verts_loc[vert_idx])  # add the vert to the local verts

            face_vert_loc_indices[loop_idx] = map_index  # remap to the local index

        faces_split.append(face)

    # remove one of the items and reorder
    return [(verts_split, faces_split, key_to_name(key), bool(use_vnor), bool(use_vtex))
            for key, (verts_split, faces_split, _, use_vnor, use_vtex)
            in face_split_dict.items()]


def create_mesh(new_meshes,
                use_edges,
                verts_loc,
                verts_nor,
                verts_tex,
                faces,
                unique_smooth_groups,
                vertex_groups,
                dataname,
                ):
    """
    Takes all the data gathered and generates a mesh, adding the new object to new_objects
    deals with ngons, sharp edges and assigning materials
    """

    if unique_smooth_groups:
        sharp_edges = set()
        smooth_group_users = {context_smooth_group: {} for context_smooth_group in unique_smooth_groups.keys()}
        context_smooth_group_old = -1

    fgon_edges = set()  # Used for storing fgon keys when we need to tessellate/untessellate them (ngons with hole).
    edges = []
    tot_loops = 0

    context_object_key = None

    # reverse loop through face indices
    for f_idx in range(len(faces) - 1, -1, -1):
        face = faces[f_idx]

        (face_vert_loc_indices,
         face_vert_nor_indices,
         face_vert_tex_indices,
         context_smooth_group,
         context_object_key,
         face_invalid_blenpoly,
         ) = face

        len_face_vert_loc_indices = len(face_vert_loc_indices)

        if len_face_vert_loc_indices == 1:
            faces.pop(f_idx)  # cant add single vert faces

        # Face with a single item in face_vert_nor_indices is actually a polyline!
        elif face_is_edge(face):
            if use_edges:
                edges.extend((face_vert_loc_indices[i], face_vert_loc_indices[i + 1])
                             for i in range(len_face_vert_loc_indices - 1))
            faces.pop(f_idx)

        else:
            # Smooth Group
            if unique_smooth_groups and context_smooth_group:
                # Is a part of of a smooth group and is a face
                if context_smooth_group_old is not context_smooth_group:
                    edge_dict = smooth_group_users[context_smooth_group]
                    context_smooth_group_old = context_smooth_group

                prev_vidx = face_vert_loc_indices[-1]
                for vidx in face_vert_loc_indices:
                    edge_key = (prev_vidx, vidx) if (prev_vidx < vidx) else (vidx, prev_vidx)
                    prev_vidx = vidx
                    edge_dict[edge_key] = edge_dict.get(edge_key, 0) + 1

            # NGons into triangles
            if face_invalid_blenpoly:
                # ignore triangles with invalid indices
                if len(face_vert_loc_indices) > 3:
                    from bpy_extras.mesh_utils import ngon_tessellate
                    ngon_face_indices = ngon_tessellate(verts_loc, face_vert_loc_indices, debug_print=bpy.app.debug)
                    faces.extend([([face_vert_loc_indices[ngon[0]],
                                    face_vert_loc_indices[ngon[1]],
                                    face_vert_loc_indices[ngon[2]],
                                    ],
                                [face_vert_nor_indices[ngon[0]],
                                    face_vert_nor_indices[ngon[1]],
                                    face_vert_nor_indices[ngon[2]],
                                    ] if face_vert_nor_indices else [],
                                [face_vert_tex_indices[ngon[0]],
                                    face_vert_tex_indices[ngon[1]],
                                    face_vert_tex_indices[ngon[2]],
                                    ] if face_vert_tex_indices else [],
                                context_smooth_group,
                                context_object_key,
                                [],
                                )
                                for ngon in ngon_face_indices]
                                )
                    tot_loops += 3 * len(ngon_face_indices)

                    # edges to make ngons
                    if len(ngon_face_indices) > 1:
                        edge_users = set()
                        for ngon in ngon_face_indices:
                            prev_vidx = face_vert_loc_indices[ngon[-1]]
                            for ngidx in ngon:
                                vidx = face_vert_loc_indices[ngidx]
                                if vidx == prev_vidx:
                                    continue  # broken OBJ... Just skip.
                                edge_key = (prev_vidx, vidx) if (prev_vidx < vidx) else (vidx, prev_vidx)
                                prev_vidx = vidx
                                if edge_key in edge_users:
                                    fgon_edges.add(edge_key)
                                else:
                                    edge_users.add(edge_key)

                faces.pop(f_idx)
            else:
                tot_loops += len_face_vert_loc_indices

    # Build sharp edges
    if unique_smooth_groups:
        for edge_dict in smooth_group_users.values():
            for key, users in edge_dict.items():
                if users == 1:  # This edge is on the boundary of a group
                    sharp_edges.add(key)

    me = bpy.data.meshes.new(dataname)

    me.vertices.add(len(verts_loc))
    me.loops.add(tot_loops)
    me.polygons.add(len(faces))

    # verts_loc is a list of (x, y, z) tuples
    me.vertices.foreach_set("co", unpack_list(verts_loc))

    loops_vert_idx = tuple(vidx for (face_vert_loc_indices, _, _, _, _, _) in faces for vidx in face_vert_loc_indices)
    faces_loop_start = []
    lidx = 0
    for f in faces:
        face_vert_loc_indices = f[0]
        nbr_vidx = len(face_vert_loc_indices)
        faces_loop_start.append(lidx)
        lidx += nbr_vidx
    faces_loop_total = tuple(len(face_vert_loc_indices) for (face_vert_loc_indices, _, _, _, _, _) in faces)

    me.loops.foreach_set("vertex_index", loops_vert_idx)
    me.polygons.foreach_set("loop_start", faces_loop_start)
    me.polygons.foreach_set("loop_total", faces_loop_total)

    faces_use_smooth = tuple(bool(context_smooth_group) for (_, _, _, context_smooth_group, _, _) in faces)
    me.polygons.foreach_set("use_smooth", faces_use_smooth)

    if verts_nor and me.loops:
        # Note: we store 'temp' normals in loops, since validate() may alter final mesh,
        #       we can only set custom lnors *after* calling it.
        me.create_normals_split()
        loops_nor = tuple(no for (_, face_vert_nor_indices, _, _, _, _) in faces
                             for face_noidx in face_vert_nor_indices
                             for no in verts_nor[face_noidx])
        me.loops.foreach_set("normal", loops_nor)

    if verts_tex and me.polygons:
        # Some files Do not explicitly write the 'v' value when it's 0.0, see T68249...
        verts_tex = [uv if len(uv) == 2 else uv + [0.0] for uv in verts_tex]
        me.uv_layers.new(do_init=False)
        loops_uv = tuple(uv for (_, _, face_vert_tex_indices, _, _, _) in faces
                            for face_uvidx in face_vert_tex_indices
                            for uv in verts_tex[face_uvidx])
        me.uv_layers[0].data.foreach_set("uv", loops_uv)

    use_edges = use_edges and bool(edges)
    if use_edges:
        me.edges.add(len(edges))
        # edges should be a list of (a, b) tuples
        me.edges.foreach_set("vertices", unpack_list(edges))

    me.validate(clean_customdata=False)  # *Very* important to not remove lnors here!
    me.update(calc_edges=use_edges, calc_edges_loose=use_edges)

    # Un-tessellate as much as possible, in case we had to triangulate some ngons...
    if fgon_edges:
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(me)
        verts = bm.verts[:]
        get = bm.edges.get
        edges = [get((verts[vidx1], verts[vidx2])) for vidx1, vidx2 in fgon_edges]
        try:
            bmesh.ops.dissolve_edges(bm, edges=edges, use_verts=False)
        except:
            # Possible dissolve fails for some edges, but don't fail silently in case this is a real bug.
            import traceback
            traceback.print_exc()

        bm.to_mesh(me)
        bm.free()

    # XXX If validate changes the geometry, this is likely to be broken...
    if unique_smooth_groups and sharp_edges:
        for e in me.edges:
            if e.key in sharp_edges:
                e.use_edge_sharp = True

    if verts_nor:
        clnors = array.array('f', [0.0] * (len(me.loops) * 3))
        me.loops.foreach_get("normal", clnors)

        if not unique_smooth_groups:
            me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))

        me.normals_split_custom_set(tuple(zip(*(iter(clnors),) * 3)))
        me.use_auto_smooth = True

    new_meshes.append(me)

def strip_slash(line_split):
    if line_split[-1][-1] == 92:  # '\' char
        if len(line_split[-1]) == 1:
            line_split.pop()  # remove the \ item
        else:
            line_split[-1] = line_split[-1][:-1]  # remove the \ from the end last number
        return True
    return False


def get_float_func(filepath):
    """
    find the float function for this obj file
    - whether to replace commas or not
    """
    file = open(filepath, 'rb')
    for line in file:  # .readlines():
        line = line.lstrip()
        if line.startswith(b'v'):  # vn vt v
            if b',' in line:
                file.close()
                return lambda f: float(f.replace(b',', b'.'))
            elif b'.' in line:
                file.close()
                return float

    file.close()
    # in case all vert values were ints
    return float


def any_number_as_int(svalue):
    if b',' in svalue:
        svalue = svalue.replace(b',', b'.')
    return int(float(svalue))


def load(filepath,
         *,
         use_smooth_groups=True,
         use_edges=True,
         use_split_objects=True,
         use_split_groups=False,
         use_groups_as_vgroups=False,
         ):
    """
    Called by the user interface or another script.
    load_obj(path) - should give acceptable results.
    This function passes the file and sends the data off
        to be split into objects and then converted into mesh objects
    """
    def unique_name(existing_names, name_orig):
        i = 0
        if name_orig is None:
            name_orig = b"ObjObject"
        name = name_orig
        while name in existing_names:
            name = b"%s.%03d" % (name_orig, i)
            i += 1
        existing_names.add(name)
        return name

    def handle_vec(line_start, context_multi_line, line_split, tag, data, vec, vec_len):
        ret_context_multi_line = tag if strip_slash(line_split) else b''
        if line_start == tag:
            vec[:] = [float_func(v) for v in line_split[1:]]
        elif context_multi_line == tag:
            vec += [float_func(v) for v in line_split]
        if not ret_context_multi_line:
            data.append(tuple(vec[:vec_len]))
        return ret_context_multi_line

    def create_face(context_smooth_group, context_object_key):
        face_vert_loc_indices = []
        face_vert_nor_indices = []
        face_vert_tex_indices = []
        return (
            face_vert_loc_indices,
            face_vert_nor_indices,
            face_vert_tex_indices,
            context_smooth_group,
            context_object_key,
            [],  # If non-empty, that face is a Blender-invalid ngon (holes...), need a mutable object for that...
        )

    if use_split_objects or use_split_groups:
        use_groups_as_vgroups = False

    verts_loc = []
    verts_nor = []
    verts_tex = []
    faces = []  # tuples of the faces
    vertex_groups = {}  # when use_groups_as_vgroups is true

    # Get the string to float conversion func for this file- is 'float' for almost all files.
    float_func = get_float_func(filepath)

    # Context variables
    context_smooth_group = None
    context_object_key = None
    context_object_obpart = None
    context_vgroup = None

    objects_names = set()

    # Until we can use sets
    unique_smooth_groups = {}

    # when there are faces that end with \
    # it means they are multiline-
    # since we use xreadline we cant skip to the next line
    # so we need to know whether
    context_multi_line = b''

    # Per-face handling data.
    face_vert_loc_indices = None
    face_vert_nor_indices = None
    face_vert_tex_indices = None
    verts_loc_len = verts_nor_len = verts_tex_len = 0
    face_items_usage = set()
    face_invalid_blenpoly = None
    prev_vidx = None
    face = None
    vec = []

    quick_vert_failures = 0
    skip_quick_vert = False

    with open(filepath, 'rb') as f:
        for line in f:
            line_split = line.split()

            if not line_split:
                continue

            line_start = line_split[0]  # we compare with this a _lot_

            if len(line_split) == 1 and not context_multi_line and line_start != b'end':
                print("WARNING, skipping malformatted line: %s" % line.decode('UTF-8', 'replace').rstrip())
                continue

            # Handling vertex data are pretty similar, factorize that.
            # Also, most OBJ files store all those on a single line, so try fast parsing for that first,
            # and only fallback to full multi-line parsing when needed, this gives significant speed-up
            # (~40% on affected code).
            if line_start == b'v':
                vdata, vdata_len, do_quick_vert = verts_loc, 3, not skip_quick_vert
            elif line_start == b'vn':
                vdata, vdata_len, do_quick_vert = verts_nor, 3, not skip_quick_vert
            elif line_start == b'vt':
                vdata, vdata_len, do_quick_vert = verts_tex, 2, not skip_quick_vert
            elif context_multi_line == b'v':
                vdata, vdata_len, do_quick_vert = verts_loc, 3, False
            elif context_multi_line == b'vn':
                vdata, vdata_len, do_quick_vert = verts_nor, 3, False
            elif context_multi_line == b'vt':
                vdata, vdata_len, do_quick_vert = verts_tex, 2, False
            else:
                vdata_len = 0

            if vdata_len:
                if do_quick_vert:
                    try:
                        vdata.append(list(map(float_func, line_split[1:vdata_len + 1])))
                    except:
                        do_quick_vert = False
                        # In case we get too many failures on quick parsing, force fallback to full multi-line one.
                        # Exception handling can become costly...
                        quick_vert_failures += 1
                        if quick_vert_failures > 10000:
                            skip_quick_vert = True
                if not do_quick_vert:
                    context_multi_line = handle_vec(line_start, context_multi_line, line_split,
                                                    context_multi_line or line_start,
                                                    vdata, vec, vdata_len)

            elif line_start == b'f' or context_multi_line == b'f':
                if not context_multi_line:
                    line_split = line_split[1:]
                    # Instantiate a face
                    face = create_face(context_smooth_group, context_object_key)
                    (face_vert_loc_indices, face_vert_nor_indices, face_vert_tex_indices,
                        _, _, face_invalid_blenpoly) = face
                    faces.append(face)
                    face_items_usage.clear()
                    verts_loc_len = len(verts_loc)
                    verts_nor_len = len(verts_nor)
                    verts_tex_len = len(verts_tex)
                # Else, use face_vert_loc_indices and face_vert_tex_indices previously defined and used the obj_face

                context_multi_line = b'f' if strip_slash(line_split) else b''

                for v in line_split:
                    obj_vert = v.split(b'/')
                    idx = int(obj_vert[0])  # Note that we assume here we cannot get OBJ invalid 0 index...
                    vert_loc_index = (idx + verts_loc_len) if (idx < 1) else idx - 1
                    # Add the vertex to the current group
                    # *warning*, this wont work for files that have groups defined around verts
                    if use_groups_as_vgroups and context_vgroup:
                        vertex_groups[context_vgroup].append(vert_loc_index)
                    # This a first round to quick-detect ngons that *may* use a same edge more than once.
                    # Potential candidate will be re-checked once we have done parsing the whole face.
                    if not face_invalid_blenpoly:
                        # If we use more than once a same vertex, invalid ngon is suspected.
                        if vert_loc_index in face_items_usage:
                            face_invalid_blenpoly.append(True)
                        else:
                            face_items_usage.add(vert_loc_index)
                    face_vert_loc_indices.append(vert_loc_index)

                    # formatting for faces with normals and textures is
                    # loc_index/tex_index/nor_index
                    if len(obj_vert) > 1 and obj_vert[1] and obj_vert[1] != b'0':
                        idx = int(obj_vert[1])
                        face_vert_tex_indices.append((idx + verts_tex_len) if (idx < 1) else idx - 1)
                    else:
                        face_vert_tex_indices.append(0)

                    if len(obj_vert) > 2 and obj_vert[2] and obj_vert[2] != b'0':
                        idx = int(obj_vert[2])
                        face_vert_nor_indices.append((idx + verts_nor_len) if (idx < 1) else idx - 1)
                    else:
                        face_vert_nor_indices.append(0)

                if not context_multi_line:
                    # Means we have finished a face, we have to do final check if ngon is suspected to be blender-invalid...
                    if face_invalid_blenpoly:
                        face_invalid_blenpoly.clear()
                        face_items_usage.clear()
                        prev_vidx = face_vert_loc_indices[-1]
                        for vidx in face_vert_loc_indices:
                            edge_key = (prev_vidx, vidx) if (prev_vidx < vidx) else (vidx, prev_vidx)
                            if edge_key in face_items_usage:
                                face_invalid_blenpoly.append(True)
                                break
                            face_items_usage.add(edge_key)
                            prev_vidx = vidx

            elif use_edges and (line_start == b'l' or context_multi_line == b'l'):
                # very similar to the face load function above with some parts removed
                if not context_multi_line:
                    line_split = line_split[1:]
                    # Instantiate a face
                    face = create_face(context_smooth_group, context_object_key)
                    face_vert_loc_indices = face[0]
                    # XXX A bit hackish, we use special 'value' of face_vert_nor_indices (a single True item) to tag this
                    #     as a polyline, and not a regular face...
                    face[1][:] = [True]
                    faces.append(face)
                # Else, use face_vert_loc_indices previously defined and used the obj_face

                context_multi_line = b'l' if strip_slash(line_split) else b''

                for v in line_split:
                    obj_vert = v.split(b'/')
                    idx = int(obj_vert[0]) - 1
                    face_vert_loc_indices.append((idx + len(verts_loc) + 1) if (idx < 0) else idx)

            elif line_start == b's':
                if use_smooth_groups:
                    context_smooth_group = line_value(line_split)
                    if context_smooth_group == b'off':
                        context_smooth_group = None
                    elif context_smooth_group:  # is not None
                        unique_smooth_groups[context_smooth_group] = None

            elif line_start == b'o':
                if use_split_objects:
                    context_object_key = unique_name(objects_names, line_value(line_split))
                    context_object_obpart = context_object_key

            elif line_start == b'g':
                if use_split_groups:
                    grppart = line_value(line_split)
                    context_object_key = (context_object_obpart, grppart) if context_object_obpart else grppart
                elif use_groups_as_vgroups:
                    context_vgroup = line_value(line.split())
                    if context_vgroup and context_vgroup != b'(null)':
                        vertex_groups.setdefault(context_vgroup, [])
                    else:
                        context_vgroup = None  # dont assign a vgroup

    new_meshes = []  # put new objects here

    # Split the mesh by objects/materials, may
    split_meshes = bool(use_split_objects or use_split_groups)

    for data in split_mesh(verts_loc, faces, filepath, split_meshes):
        verts_loc_split, faces_split, dataname, use_vnor, use_vtex = data
        # Create meshes from the data, warning 'vertex_groups' wont support splitting
        #~ print(dataname, use_vnor, use_vtex)
        create_mesh(new_meshes,
                    use_edges,
                    verts_loc_split,
                    verts_nor if use_vnor else [],
                    verts_tex if use_vtex else [],
                    faces_split,
                    unique_smooth_groups,
                    vertex_groups,
                    dataname,
                    )

    return new_meshes
