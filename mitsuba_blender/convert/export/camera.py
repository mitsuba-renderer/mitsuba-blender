'''Blender camera to Mitsuba sensor conversion.

The geometric mappings (field of view, lens shift, orthographic scale,
depth of field) live in this module; the importer in
convert.importer.camera applies their inverses.
'''

import math

from mathutils import Matrix


###################
##   Geometry    ##
###################

def fit_dimension(sensor_fit, res_x, res_y):
    '''The resolution of the axis that Blender's sensor fit locks. Lens
    shift values are expressed relative to this dimension.'''
    if sensor_fit == 'HORIZONTAL':
        return res_x
    if sensor_fit == 'VERTICAL':
        return res_y
    return max(res_x, res_y)


def shift_to_principal_point(shift_x, shift_y, sensor_fit, res_x, res_y):
    '''Blender lens shift to Mitsuba principal point offset. Mitsuba
    expresses the offset in fractions of the film width/height with the
    y axis pointing down.'''
    fit = fit_dimension(sensor_fit, res_x, res_y)
    return shift_x * fit / res_x, -shift_y * fit / res_y


def principal_point_to_shift(offset_x, offset_y, res_x, res_y):
    '''Inverse of shift_to_principal_point for an AUTO-fit camera.'''
    fit = max(res_x, res_y)
    return offset_x * res_x / fit, -offset_y * res_y / fit


def fstop_to_aperture_radius(fstop, lens):
    '''Blender f-stop and focal length (mm) to an aperture radius in
    scene units, following the Cycles thin lens model.'''
    return lens / (2.0 * fstop) / 1000.0


def aperture_radius_to_fstop(radius, lens):
    return lens / (2.0 * radius) / 1000.0


def ortho_scale_to_extent(ortho_scale, sensor_fit, res_x, res_y):
    '''Blender orthographic scale to the half extent of the Mitsuba
    orthographic sensor along its x axis.'''
    horizontal = res_x >= res_y if sensor_fit == 'AUTO' \
        else sensor_fit == 'HORIZONTAL'
    if horizontal:
        return ortho_scale / 2.0
    return ortho_scale * res_x / (2.0 * res_y)


def extent_to_ortho_scale(extent, res_x, res_y):
    '''Inverse of ortho_scale_to_extent for an AUTO-fit camera.'''
    if res_x >= res_y:
        return 2.0 * extent
    return 2.0 * extent * res_y / res_x


def focus_distance(b_camera_data, matrix_world):
    '''The focus distance in scene units, resolving a focus object to its
    distance along the view axis like Cycles does.'''
    focus_object = b_camera_data.dof.focus_object
    if focus_object is None:
        return b_camera_data.dof.focus_distance
    local = matrix_world.inverted() @ focus_object.matrix_world.translation
    return abs(local.z)


######################
##   Converters     ##
######################

def _fov_params(b_camera_data, res_x, res_y):
    sensor_fit = b_camera_data.sensor_fit
    if sensor_fit == 'VERTICAL':
        return {'fov_axis': 'y', 'fov': math.degrees(b_camera_data.angle_y)}
    # With AUTO fit the sensor width applies to the larger image dimension,
    # so angle_x is the field of view of the fit axis in both orientations.
    axis = 'y' if sensor_fit == 'AUTO' and res_x < res_y else 'x'
    return {'fov_axis': axis, 'fov': math.degrees(b_camera_data.angle_x)}


def _convert_perspective(export_ctx, b_camera, matrix_world, res_x, res_y):
    data = b_camera.data
    params = _fov_params(data, res_x, res_y)
    offset_x, offset_y = shift_to_principal_point(
        data.shift_x, data.shift_y, data.sensor_fit, res_x, res_y)

    if data.dof.use_dof:
        params['type'] = 'thinlens'
        params['aperture_radius'] = fstop_to_aperture_radius(
            data.dof.aperture_fstop, data.lens)
        params['focus_distance'] = focus_distance(data, matrix_world)
        if offset_x != 0.0 or offset_y != 0.0:
            export_ctx.log(f'Camera "{b_camera.name_full}": Mitsuba does not '
                           'support lens shift together with depth of field. '
                           'Ignoring the shift.', 'WARN')
    else:
        params['type'] = 'perspective'
        params['principal_point_offset_x'] = offset_x
        params['principal_point_offset_y'] = offset_y

    init_rot = Matrix.Rotation(math.pi, 4, 'Y')
    params['to_world'] = export_ctx.transform_matrix(matrix_world @ init_rot)
    return params


def _convert_orthographic(export_ctx, b_camera, matrix_world, res_x, res_y):
    data = b_camera.data
    params = {'type': 'orthographic'}

    if data.dof.use_dof:
        export_ctx.log(f'Camera "{b_camera.name_full}": Mitsuba does not '
                       'support depth of field on orthographic cameras. '
                       'Ignoring it.', 'WARN')

    # A lens shift translates the imaged region in the camera plane
    shift = Matrix.Translation((data.shift_x * data.ortho_scale,
                                data.shift_y * data.ortho_scale, 0.0))
    extent = ortho_scale_to_extent(data.ortho_scale, data.sensor_fit,
                                   res_x, res_y)
    scale = Matrix.Diagonal((extent, extent, 1.0, 1.0))
    init_rot = Matrix.Rotation(math.pi, 4, 'Y')
    params['to_world'] = export_ctx.transform_matrix(
        matrix_world @ shift @ init_rot @ scale)
    return params


def convert_camera(export_ctx, b_camera, b_scene, matrix_world=None):
    '''Convert a Blender camera object into a Mitsuba sensor dict.'''
    if matrix_world is None:
        matrix_world = b_camera.matrix_world
    res_x = b_scene.render.resolution_x
    res_y = b_scene.render.resolution_y

    data = b_camera.data
    if data.type == 'ORTHO':
        params = _convert_orthographic(export_ctx, b_camera, matrix_world,
                                       res_x, res_y)
    else:
        if data.type != 'PERSP':
            export_ctx.log(f'Camera "{b_camera.name_full}" of type '
                           f'"{data.type}" is not supported. Exporting it '
                           'as a perspective camera.', 'WARN')
        loc, rot, _ = matrix_world.decompose()
        matrix_world = Matrix.LocRotScale(loc, rot, (1.0, 1.0, 1.0))
        params = _convert_perspective(export_ctx, b_camera, matrix_world,
                                      res_x, res_y)

    params['near_clip'] = data.clip_start
    params['far_clip'] = data.clip_end
    params['sampler'] = _convert_sampler(b_camera, b_scene)
    params['film'] = _convert_film(b_camera, b_scene)
    return params


def _convert_sampler(b_camera, b_scene):
    if b_scene.render.engine == 'MITSUBA':
        return b_camera.data.mitsuba.sampler_to_dict()
    # scene.cycles only exists while the Cycles addon is enabled
    cycles = getattr(b_scene, 'cycles', None)
    return {
        'type': 'independent',
        'sample_count': cycles.samples if cycles else 64,
    }


def _convert_film(b_camera, b_scene):
    scale = b_scene.render.resolution_percentage / 100.0
    film = {
        'type': 'hdrfilm',
        'width': int(b_scene.render.resolution_x * scale),
        'height': int(b_scene.render.resolution_y * scale),
    }
    if b_scene.render.engine == 'MITSUBA':
        film['rfilter'] = b_camera.data.mitsuba.rfilter_to_dict()
    elif b_scene.render.engine == 'CYCLES':
        if b_scene.cycles.pixel_filter_type == 'GAUSSIAN':
            film['rfilter'] = {
                'type': 'gaussian',
                'stddev': b_scene.cycles.filter_width,
            }
        elif b_scene.cycles.pixel_filter_type == 'BOX':
            film['rfilter'] = {'type': 'box'}
    return film


def export_camera(export_ctx, camera_instance, b_scene):
    '''Convert a depsgraph camera instance and add it to the scene dict.
    Never raises: failures produce a warning and the camera is skipped.'''
    b_camera = camera_instance.object
    try:
        params = convert_camera(export_ctx, b_camera, b_scene,
                                camera_instance.matrix_world.copy())
    except Exception as e:
        export_ctx.log(f'Failed to export camera "{b_camera.name_full}": '
                       f'{e}. Skipping it.', 'WARN')
        return
    if export_ctx.export_ids:
        export_ctx.data_add(params, name=b_camera.name_full)
    else:
        export_ctx.data_add(params)
