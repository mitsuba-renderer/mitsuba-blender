'''Hair particle systems exported as Mitsuba ``linearcurve`` shapes.

Blender renders a hair particle system from a path cache that holds the parent
strands followed by the interpolated children. The cache is only reachable one
control point at a time through ``ParticleSystem.co_hair``, which returns world
space coordinates and a zero vector once the step runs past the end of a strand.

Each particle system becomes one entry of the scene's ``curves.packed``
container and one ``linearcurve`` shape. The points are written in world
space with the scene's axis conversion already applied, because
``linearcurve`` leaves the control point radii untouched by ``to_world`` and
a scaled object would otherwise keep the radii it had before scaling.
'''

import bpy
import numpy as np

from . import ray_visibility

# Upper bound on the control points of one strand. The path cache holds
# 2 ** display_step + 1 points for a parent strand and fewer for a child, so
# this only guards against a runaway loop.
MAX_STEPS = 256


def strand_radius(settings, t):
    '''Radius of a strand at ``t`` in [0, 1] along its length, in object space.

    Follows Cycles: the root and tip values are diameters (the UI calls them
    "Diameter Root" and "Diameter Tip") and ``shape`` bends the interpolation
    between them, negative towards the tip and positive towards the root.
    '''
    shape = settings.shape
    root, tip = settings.root_radius, settings.tip_radius
    f = 1.0 - t
    if shape < 0.0:
        f = f ** (1.0 + shape)
    elif shape > 0.0:
        f = f ** (1.0 / max(1.0 - shape, 1e-3))
    return 0.5 * settings.radius_scale * (f * (root - tip) + tip)


def read_strand(psys, b_object, particle_no):
    '''World space control points of one strand of the path cache.'''
    points = []
    for step in range(MAX_STEPS):
        co = psys.co_hair(b_object, particle_no=particle_no, step=step)
        # The cache reports its end as a zero vector. A genuine control point
        # at the world origin would end a strand early, which no scene of ours
        # comes close to.
        if co.x == 0.0 and co.y == 0.0 and co.z == 0.0:
            break
        points.append(co)
    return points


def collect_curves(export_ctx, psys, b_object):
    '''Gather the path cache as a (P, 4) float32 array of control points
    (position and radius) and a uint32 array with the first control point
    index of each strand followed by P. Strands of fewer than two points are
    left out, which ``linearcurve`` would reject.
    '''
    settings = psys.settings
    axis_mat = export_ctx.axis_mat
    # linearcurve keeps the radii as written, so they have to carry the
    # object's scale. The axis conversion is a rotation and does not scale.
    scale = sum(b_object.matrix_world.to_scale()) / 3.0
    count = len(psys.particles) + len(psys.child_particles)
    close_tip = settings.use_close_tip

    records, offsets = [], [0]
    for particle_no in range(count):
        points = read_strand(psys, b_object, particle_no)
        if len(points) < 2:
            continue
        last = len(points) - 1
        for i, co in enumerate(points):
            t = i / last
            radius = 0.0 if (close_tip and i == last) else \
                strand_radius(settings, t) * scale
            p = axis_mat @ co
            records.append((p.x, p.y, p.z, radius))
        offsets.append(len(records))
    return (np.array(records, dtype=np.float32).reshape(-1, 4),
            np.array(offsets, dtype=np.uint32))


def particle_material(export_ctx, b_object, settings):
    '''(bsdf_id, emitter) of the material slot the particle system draws from.

    ``ParticleSettings.material`` is a one-based index into the slots of the
    object that carries the system.
    '''
    from .mesh import default_bsdf_id, material_refs
    slots = b_object.material_slots
    index = settings.material - 1
    if 0 <= index < len(slots) and slots[index].material is not None:
        return material_refs(export_ctx, slots[index].material)
    return default_bsdf_id(export_ctx), None


def export_hair(export_ctx, deg_instance):
    '''Add one ``linearcurve`` shape per hair particle system of the object.

    Systems that Blender does not draw as strands are left out. Those with a
    render type of OBJECT or COLLECTION already reach the exporter as
    depsgraph instances of the drawn object.
    '''
    b_object = deg_instance.object
    for psys in b_object.particle_systems:
        settings = psys.settings
        if settings.type != 'HAIR' or settings.render_type != 'PATH':
            continue
        if not psys.particles and not psys.child_particles:
            continue

        bsdf_id, emitter = particle_material(export_ctx, b_object, settings)
        visibility = ray_visibility(b_object, emitter is not None)
        if visibility is None:
            continue
        if not b_object.visible_shadow:
            from .materials.shadowless import shadowless_material
            bsdf_id = shadowless_material(export_ctx, bsdf_id)

        name = bpy.path.clean_name(
            f'{b_object.name_full}-{psys.name}')
        points, offsets = collect_curves(export_ctx, psys, b_object)
        written = len(offsets) - 1
        if written == 0:
            export_ctx.log(f'Particle system "{psys.name}" of object '
                           f'"{b_object.name_full}" has no strand with at '
                           'least two control points. Skipping it.', 'WARN')
            continue

        if export_ctx.deg is not None and export_ctx.deg.mode == 'VIEWPORT' \
                and settings.child_type != 'NONE' \
                and settings.child_percent != settings.rendered_child_count:
            export_ctx.log(
                f'Particle system "{psys.name}" of object '
                f'"{b_object.name_full}" is evaluated for the viewport, so it '
                f'has {settings.child_percent} children per parent instead of '
                f'the {settings.rendered_child_count} used for rendering.',
                'WARN')

        entry = {
            'type': 'linearcurve',
            'filename': export_ctx.curves_filename(),
            'index': export_ctx.add_packed_curves(name, points, offsets),
            'bsdf': export_ctx.create_ref(bsdf_id),
        }
        if emitter is not None:
            entry['emitter'] = emitter
        if visibility != 'all':
            entry['visibility'] = visibility
        if export_ctx.export_ids:
            export_ctx.data_add(entry, name=f'curves-{name}')
        else:
            export_ctx.data_add(entry)
        export_ctx.log(f'Particle system "{psys.name}" of object '
                       f'"{b_object.name_full}": {written} strands written to '
                       f'{export_ctx.curves_filename()}.', 'INFO')
