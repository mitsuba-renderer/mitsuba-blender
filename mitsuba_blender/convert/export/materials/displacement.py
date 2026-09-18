'''Displacement of the Material Output node.

Cycles moves the vertices of a mesh when the Displacement input of the
Material Output is linked and the material's displacement method is
"Displacement Only" or "Displacement and Bump". The exporter reproduces
this with the ``displace`` shape, which wraps the exported mesh and reads
the Height, Scale and Midlevel of the Displacement node. With the "Bump
Only" method Cycles uses the socket for bump mapping instead, which is not
exported.

The exporter does not tessellate. Like Cycles without adaptive subdivision,
it displaces the vertices of the evaluated mesh, so a Subdivision modifier
controls how much of the height field survives. The exporter evaluates the
modifier at its viewport level, and an adaptive Subdivision modifier falls
back to that uniform level. An object whose faces are all flat shaded is
displaced with face normals, and any other object with recomputed vertex
normals.
'''
from ... import ConversionError
from ....compat import uses_nodes
from ._resolve import eval_float, scalar_from_socket, trace_source

DISPLACING_METHODS = ('DISPLACEMENT', 'BOTH')

# World-space amplitude (m) above which a displacement is reported as
# suspicious
LARGE_AMPLITUDE = 0.1


def material_displacement(export_ctx, b_mat):
    '''Return the displacement of a material as a dict with the entries
    height (float or texture dict), scale, midlevel and space (OBJECT or
    WORLD), or None when the material does not displace. The result is
    cached per material name.'''
    if b_mat is None or not export_ctx.export_displacement \
            or not uses_nodes(b_mat):
        return None
    cache = export_ctx.displacements
    if b_mat.name not in cache:
        cache[b_mat.name] = _convert(export_ctx, b_mat)
    return cache[b_mat.name]


def _convert(export_ctx, b_mat):
    output = b_mat.node_tree.get_output_node('CYCLES')
    if output is None or not output.inputs['Displacement'].is_linked \
            or b_mat.displacement_method not in DISPLACING_METHODS:
        return None
    try:
        node, _, stack = trace_source(output.inputs['Displacement'])
    except ConversionError as e:
        export_ctx.log(f'Material "{b_mat.name}": {e}; ignoring its '
                       'displacement', 'WARN')
        return None
    if node is None:
        return None
    if node.type != 'DISPLACEMENT':
        export_ctx.log(f'Material "{b_mat.name}": the Displacement output '
                       f'is driven by node "{node.name}" of type '
                       f'{node.type}, which is not supported; ignoring its '
                       'displacement', 'WARN')
        return None
    if node.inputs['Normal'].is_linked:
        export_ctx.log(f'Material "{b_mat.name}": the Normal input of '
                       f'displacement node "{node.name}" is ignored; the '
                       'mesh is displaced along its vertex normals', 'WARN')
    height = eval_float(export_ctx, node.inputs['Height'], stack=stack)
    if isinstance(height, dict) and height.get('type') == 'bitmap':
        # The displace shape looks the height up over the local vertex
        # spacing, which keeps coarse regions of a mesh from sampling the
        # detail at random
        height.setdefault('filter_type', 'trilinear')
    return {
        'height': height,
        'scale': scalar_from_socket(export_ctx, node.inputs['Scale'],
                                    stack=stack),
        'midlevel': scalar_from_socket(export_ctx, node.inputs['Midlevel'],
                                       stack=stack),
        'space': node.space,
    }


def check_displacements(export_ctx, b_object, b_mesh, name, has_uvs,
                        displacements):
    '''Drop the displacements of the parts of an object that cannot be
    displaced, and report approximations. ``displacements`` maps part names
    to the results of `material_displacement`.'''
    if not any(d is not None for d in displacements.values()):
        return
    # Cycles shades flat faces with the normal of the displaced triangle
    if _all_faces_flat(b_mesh):
        for k, d in displacements.items():
            if d is not None:
                displacements[k] = dict(d, face_normals=True)
    textured = [k for k, d in displacements.items()
                if d is not None and isinstance(d['height'], dict)]
    if not has_uvs and textured:
        export_ctx.log(f'Object "{name}" has no UV map; ignoring the '
                       'displacement of its material', 'WARN')
        for k in textured:
            displacements[k] = None
    if any(getattr(md, 'use_adaptive_subdivision', False) and md.show_render
           for md in b_object.modifiers):
        export_ctx.log(f'Object "{name}" uses adaptive subdivision, which is '
                       'not supported; displacing its uniformly subdivided '
                       'mesh instead', 'WARN')


def _all_faces_flat(b_mesh):
    import numpy as np
    attr = b_mesh.attributes.get('sharp_face')
    if attr is None or len(b_mesh.polygons) == 0:
        return False
    flags = np.empty(len(b_mesh.polygons), dtype=bool)
    attr.data.foreach_get('value', flags)
    return bool(flags.all())


def displaced_entry(export_ctx, entry, displacement, to_world, name):
    '''Wrap the scene dict entry of a mesh in a displace shape. The plugin
    displaces in the space of the nested mesh, i.e. the object space that
    ``to_world`` maps to the world, which is where Cycles applies an
    OBJECT space displacement. A WORLD space displacement is expressed in
    world units and is converted with the object's scale.'''
    import numpy as np
    scale = displacement['scale']
    if displacement['space'] == 'WORLD':
        if to_world is None:
            export_ctx.log(f'Object "{name}" is instanced and its material '
                           'displaces in world space; the displacement '
                           'scale is applied in object space instead', 'WARN')
        else:
            m = np.array(to_world.matrix)[:3, :3]
            axes = np.linalg.norm(m, axis=0)
            if axes.max() > 1.05 * axes.min():
                export_ctx.log(f'Object "{name}" has a non-uniform scale '
                               'and its material displaces in world space; '
                               'using the mean scale', 'WARN')
            scale /= float(axes.mean())

    # Largest offset in world units, for a height in [0, 1]
    height, midlevel = displacement['height'], displacement['midlevel']
    if isinstance(height, dict):
        amplitude = max(abs(midlevel), abs(1 - midlevel))
    else:
        amplitude = abs(height - midlevel)
    amplitude *= abs(scale)
    if to_world is not None:
        amplitude *= float(np.linalg.norm(
            np.array(to_world.matrix)[:3, :3], axis=0).max())
    export_ctx.log(f'Object "{name}": displacement of up to '
                   f'{amplitude * 100:.3g} cm')
    if amplitude > LARGE_AMPLITUDE:
        export_ctx.log(f'Object "{name}" is displaced by up to '
                       f'{amplitude:.3g} m, which is unusually large', 'WARN')
    result = {
        'type': 'displace',
        'mesh': entry,
        'height': displacement['height'],
        'scale': scale,
        'midlevel': displacement['midlevel'],
    }
    if displacement.get('face_normals'):
        result['face_normals'] = True
    return result
