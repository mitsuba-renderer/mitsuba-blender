# This script exports the hair particle systems of the selected object to a
# Mitsuba compatible curve file.

import bpy
import math
import numpy as np
from .materials import export_material
from .. import logging

def export_particle_systems(ctx, instance):
    '''
    Exports the particle systems of the object to a Mitsuba compatible curve file.
    '''
    if instance is None:
        return []

    object = instance.object

    particle_mats = []

    for psys in object.particle_systems:
        if psys.settings.render_type == 'PATH':
            curve_id = f"{object.name}-{psys.name}"
            logging.debug(f'Exporting particle system: {curve_id}')

            root_radius  = psys.settings.root_radius
            tip_radius   = psys.settings.tip_radius
            radius_scale = psys.settings.radius_scale * 0.5

            if not ctx.viewport:
                steps = 2 ** psys.settings.render_step
            else:
                steps = 2 ** psys.settings.display_step
            points_per_strand = steps + 1

            num_parents = len(psys.particles)
            num_children = len(psys.child_particles)
            dupli_count = num_parents + num_children

            if num_children == 0:
                start = 0
            else:
                # Number of virtual parents reduces the number of exported children
                num_virtual_parents = math.trunc(0.3 * psys.settings.virtual_parents
                                                * psys.settings.child_length * num_parents)
                start = num_parents + num_virtual_parents

            strands_count = dupli_count - start

            # Point coordinates as a flattened numpy array
            point_count = strands_count * points_per_strand
            co_hair = psys.co_hair
            points = np.fromiter((elem
                                 for pindex in range(start, dupli_count)
                                 for step in range(points_per_strand)
                                 for elem in co_hair(object=object, particle_no=pindex, step=step)),
                                 dtype=np.float32,
                                 count=point_count * 3).reshape((-1, 3))

            radii = []
            curve_1st_idx = []
            radius_delta = (tip_radius - root_radius) / points_per_strand
            for s in range(strands_count):
                curve_1st_idx.append(len(radii))
                radius = root_radius
                for i in range(points_per_strand):
                    radii.append(radius * radius_scale)
                    radius += radius_delta

            points        = np.array(points,  dtype=np.float32)
            radii         = np.array(radii,   dtype=np.float32)
            curve_1st_idx = np.array(curve_1st_idx, dtype=np.uint32)

            material_name = psys.settings.material_slot

            # Create default BSDF if necessary
            if material_name == '' or 'Default' in material_name:
                if not 'default-bsdf' in ctx.scene_dict: # We only need to add it once
                    ctx.add_object(
                        'default-bsdf',
                        {
                            'type': 'twosided',
                            'id': 'default-bsdf',
                            'bsdf': { 'type': 'diffuse' }
                        }
                    )
                material_id = 'default-bsdf'
            else:
                particle_mats.append(material_name)
                material_id = f"mat-{material_name}"
                # In Mitsuba `.` are not supported in object's name as it's used in `mi.traverse`
                material_id = material_id.replace('.', '_')

            if ctx.export_curves:
                params = {
                    'type': 'catmullromcurve',
                    'interpolate_end_points': True,
                    'points': points,
                    'radii':  radii,
                    'curve_1st_idx': curve_1st_idx,
                    'bsdf': { 'type': 'ref', 'id': material_id },
                    'to_world': ctx.transform_matrix(instance.matrix_world)
                }

                ctx.add_object(object.name_full, params, curve_id)

    return particle_mats

def export_hair_curves(ctx, instance):
    obj = instance.object
    strands = obj.data.curves

    points = []
    radii  = []
    curve_1st_idx = []

    for strand in strands:
        curve_1st_idx.append(len(radii))
        for i in range(strand.points_length):
            points.append(list(strand.points[i].position))
            radii.append(strand.points[i].radius)

    points        = np.array(points,  dtype=np.float32)
    radii         = np.array(radii,   dtype=np.float32)
    curve_1st_idx = np.array(curve_1st_idx, dtype=np.uint32)

    assert len(obj.data.materials) <= 1

    # Create default BSDF if necessary
    if len(obj.data.materials) == 0:
        if not 'default-bsdf' in ctx.scene_dict: # We only need to add it once
            ctx.add_object(
                'default-bsdf',
                {
                    'type': 'twosided',
                    'id': 'default-bsdf',
                    'bsdf': { 'type': 'diffuse' }
                }
            )
        material_id = 'default-bsdf'
    else:
        material_id = export_material(ctx, obj.data.materials[0])

        # In Mitsuba `.` are not supported in object's name as it's used in `mi.traverse`
        material_id = material_id.replace('.', '_')

    if ctx.export_curves:
        import mitsuba as mi

        params = {
            'type': 'catmullromcurve',
            'interpolate_end_points': True,
            'points': mi.TensorXf(points),
            'radii':  mi.TensorXf(radii),
            'curve_1st_idx': mi.TensorXf(curve_1st_idx),
            'bsdf': { 'type': 'ref', 'id': material_id },
            'to_world': ctx.transform_matrix(instance.matrix_world)
        }
        ctx.add_object(obj.name_full, params, obj.name)