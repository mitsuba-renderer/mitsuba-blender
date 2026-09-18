'''Blender light to Mitsuba emitter conversion.

The radiometric conversions between Blender lights (radiant power in
watts, following the Cycles conventions) and Mitsuba emitters (radiant
intensity, irradiance or radiance) live in this module; the importer in
convert.importer.lights applies their inverses.
'''

import math
import os

import bpy
from mathutils import Matrix, Vector

from . import ray_visibility
from .ies import parse_ies, format_table, light_direction_factor
from .. import ConversionError
from ...compat import uses_nodes


###################
##  Radiometry   ##
###################

def power_to_intensity(power):
    '''Radiant power (W) of a Blender point or spot light to radiant
    intensity (W/sr). Cycles normalizes by the full sphere regardless of
    the spot cone angle.'''
    return power / (4.0 * math.pi)


def intensity_to_power(intensity):
    return intensity * 4.0 * math.pi


def power_to_radiance(power, area):
    '''Radiant power (W) of a one-sided Lambertian area emitter to
    radiance (W/(sr*m^2)).'''
    return power / (math.pi * area)


def radiance_to_power(radiance, area):
    return radiance * math.pi * area


def sphere_area(radius):
    return 4.0 * math.pi * radius * radius


def spot_beam_width(spot_size, spot_blend):
    '''The angle at which the falloff of a Blender spot light begins,
    following the Cycles falloff curve. All angles are in radians.'''
    alpha = spot_size / 2.0
    return math.acos(spot_blend + (1.0 - spot_blend) * math.cos(alpha))


def spot_blend(spot_size, beam_width):
    '''Inverse of spot_beam_width.'''
    denom = 1.0 - math.cos(spot_size / 2.0)
    if denom < 1e-9:
        return 0.0
    blend = (math.cos(beam_width) - math.cos(spot_size / 2.0)) / denom
    return min(max(blend, 0.0), 1.0)


###########################
##   Light node trees    ##
###########################

# Value of an IES texture whose profile Cycles cannot load
# (cycles/src/kernel/util/ies.h)
IES_FALLBACK = 100.0

# Radius given to a point or spot light without one so that it can carry
# an IES profile, which only the cycles_lights shape evaluates
IES_POINT_RADIUS = 1e-3


def _ies_profile(export_ctx, b_light, node):
    '''The parsed profile of an IES texture node, or None when Cycles would
    substitute its constant. Profiles are cached on the export context.'''
    cache = export_ctx.ies_profiles
    internal = node.mode == 'INTERNAL'
    if internal:
        if node.ies is None:
            export_ctx.log(f'Light "{b_light.name_full}": its IES node has no '
                           'text block. Using the constant that Cycles '
                           'substitutes for a missing profile.', 'WARN')
            return None
        key = ('text', node.ies.name_full)
    else:
        path = bpy.path.abspath(node.filepath, library=b_light.data.library)
        key = ('file', os.path.normpath(path))
    if key in cache:
        return cache[key]
    try:
        if internal:
            source = node.ies.as_string()
        else:
            with open(path, 'rb') as f:
                source = f.read()
        profile = parse_ies(source)
    except OSError as e:
        export_ctx.log(f'Light "{b_light.name_full}": cannot read its IES '
                       f'profile "{node.filepath}" ({e.strerror}). Using the '
                       'constant that Cycles substitutes for a missing '
                       'profile.', 'WARN')
        profile = None
    except ValueError as e:
        export_ctx.log(f'Light "{b_light.name_full}": cannot parse its IES '
                       f'profile ({e}). Using the constant that Cycles '
                       'substitutes for a missing profile.', 'WARN')
        profile = None
    cache[key] = profile
    return profile


def ies_light_properties(profile):
    '''The IES entries of a cycles_lights light for a parsed profile: the
    resampled table, its column count and its angular range. Lights that
    share a profile share the result.'''
    if not hasattr(profile, 'light_properties'):
        table, bounds = profile.resample()
        profile.light_properties = {
            'table': format_table(table),
            'columns': int(table.shape[1]),
            'range': ' '.join(f'{math.degrees(a):g}' for a in bounds),
        }
    return profile.light_properties


def _gray(rgb):
    '''Cycles converts colors to floats by their luminance.'''
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def _rgb(value):
    if isinstance(value, (int, float)):
        return (float(value),) * 3
    return tuple(float(v) for v in value[:3])


def _falloff_distance(export_ctx, b_light, matrix_world):
    '''Distance from the light to the first surface along its -Z axis that
    lies beyond its radius, or None if there is none.'''
    depsgraph = export_ctx.deg
    if depsgraph is None:
        return None
    origin = matrix_world.translation.copy()
    direction = (matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()
    radius = getattr(b_light.data, 'shadow_soft_size', 0.0)
    distance = 0.0
    for _ in range(32):
        hit, location, *_ = depsgraph.scene.ray_cast(
            depsgraph, origin + direction * (distance + 1e-4), direction)
        if not hit:
            return None
        distance = (location - origin).length
        if distance > radius:
            return distance
    return None


def _socket_value(export_ctx, b_light, matrix_world, socket, ies=None):
    '''Value of an input socket of a light node tree as an (r, g, b) tuple.
    ``ies`` is a list that receives the profile of an IES texture node
    when the light can evaluate one per direction, in which case the node
    only contributes its strength here. Without the list, or for further
    IES nodes, the node contributes the profile's value along the light
    axis.'''
    default = _rgb(getattr(socket, 'default_value', 1.0))
    if not socket.is_linked:
        return default
    link = socket.links[0]
    node, output = link.from_node, link.from_socket

    def value(name):
        return _socket_value(export_ctx, b_light, matrix_world,
                             node.inputs[name], ies)

    kind = node.bl_idname
    if link.is_muted or node.mute:
        pass
    elif kind == 'NodeReroute':
        return _socket_value(export_ctx, b_light, matrix_world,
                             node.inputs[0], ies)
    elif kind in ('ShaderNodeValue', 'ShaderNodeRGB'):
        return _rgb(output.default_value)
    elif kind == 'ShaderNodeTexIES':
        strength = _gray(value('Strength'))
        profile = _ies_profile(export_ctx, b_light, node)
        if profile is None:
            return _rgb(strength * IES_FALLBACK)
        if ies is not None and not ies:
            ies.append(profile)
            return _rgb(strength)
        if ies:
            reason = 'only one IES profile per light is supported'
        else:
            reason = 'only point and spot lights can carry an IES profile'
        export_ctx.log(f'Light "{b_light.name_full}": {reason}. Using the '
                       'value of the profile along the light axis.', 'WARN')
        return _rgb(strength * light_direction_factor(profile, (0, 0, -1)))
    elif kind == 'ShaderNodeLightFalloff':
        strength, smooth = _gray(value('Strength')), _gray(value('Smooth'))
        # Cycles ignores the node for distant lights
        if b_light.data.type == 'SUN':
            return _rgb(strength)
        distance = _falloff_distance(export_ctx, b_light, matrix_world)
        if distance is None:
            export_ctx.log(f'Light "{b_light.name_full}": no surface found '
                           'along the light axis to evaluate its Light Falloff '
                           'node. Ignoring the falloff.', 'WARN')
            return _rgb(strength)
        # Mitsuba's emitters cannot vary with the distance to the shaded
        # point, so the node is evaluated at the distance to the lit surface
        export_ctx.log(f'Light "{b_light.name_full}": evaluating its Light '
                       f'Falloff node at a distance of {distance:.3g}.', 'INFO')
        exponent = {'Quadratic': 0, 'Linear': 1, 'Constant': 2}[output.identifier]
        strength *= distance ** exponent
        if smooth > 0.0:
            strength *= distance * distance / (smooth + distance * distance)
        return _rgb(strength)
    elif kind == 'ShaderNodeValToRGB':
        fac = min(max(_gray(value('Fac')), 0.0), 1.0)
        color = node.color_ramp.evaluate(fac)
        return _rgb(color[3]) if output.identifier == 'Alpha' else _rgb(color)
    export_ctx.log(f'Light "{b_light.name_full}": node "{node.name}" in its node '
                   'tree is not supported. Using the default value of the '
                   f'socket "{socket.name}" it feeds.', 'WARN')
    return default


def light_node_factor(export_ctx, b_light, matrix_world, ies=None):
    '''Color factor that the Cycles node tree of a light applies to its power,
    i.e. the color times the strength of its Emission shader. ``ies`` is
    a list that receives the profile of an IES texture node in the tree,
    see _socket_value.'''
    data = b_light.data
    tree = data.node_tree if uses_nodes(data) else None
    output = tree.get_output_node('CYCLES') if tree else None
    if output is None or not output.inputs['Surface'].is_linked:
        return (1.0, 1.0, 1.0)
    shader = output.inputs['Surface'].links[0].from_node
    if shader.bl_idname != 'ShaderNodeEmission':
        export_ctx.log(f'Light "{b_light.name_full}": only an Emission shader '
                       'is supported in light node trees. Ignoring the node '
                       'tree.', 'WARN')
        return (1.0, 1.0, 1.0)
    color = _socket_value(export_ctx, b_light, matrix_world,
                          shader.inputs['Color'], ies)
    strength = _gray(_socket_value(export_ctx, b_light, matrix_world,
                                   shader.inputs['Strength'], ies))
    return tuple(c * strength for c in color)


####################
##   Converters   ##
####################

def _colored(scalar, color):
    return [scalar * c for c in color[:3]]


def _cycles_light(export_ctx, b_light, matrix_world, color, profile):
    '''One light of the addon's cycles_lights shape, which the export
    context merges into a single shape per visibility class (see
    ExportContext.add_cycles_light). Cycles samples a light with a radius
    as a disk facing the shaded point and radiates P / (4 pi^2 r^2). A
    light with an IES profile carries the resampled table and its local
    frame, in which the shape evaluates the profile.'''
    data = b_light.data
    if not getattr(data, 'use_soft_falloff', True):
        export_ctx.log(f'Light "{b_light.name_full}" has "Soft Falloff" '
                       'disabled. It is exported as if it were enabled.',
                       'WARN')
    radius = data.shadow_soft_size
    if radius <= 0.0:
        export_ctx.log(f'Light "{b_light.name_full}": only lights with a '
                       'radius can carry an IES profile. Exporting it with '
                       f'a radius of {IES_POINT_RADIUS:g}.', 'INFO')
        radius = IES_POINT_RADIUS
    light = {
        'type': 'cycles_lights',
        'p': list(export_ctx.transform_matrix(matrix_world).translation()),
        'r': radius,
        'power': export_ctx.spectrum(_colored(data.energy, color)),
    }
    if profile is not None:
        light['ies'] = ies_light_properties(profile)
        light['frame'] = export_ctx.transform_matrix(
            matrix_world.to_3x3().to_4x4())
    return light


def _convert_point(export_ctx, b_light, matrix_world, color, profile=None):
    data = b_light.data
    if data.shadow_soft_size > 0.0 or profile is not None:
        return _cycles_light(export_ctx, b_light, matrix_world, color,
                             profile)
    return {
        'type': 'point',
        'position': list(
            export_ctx.transform_matrix(matrix_world).translation()),
        'intensity': export_ctx.spectrum(
            _colored(power_to_intensity(data.energy), color)),
    }


def _convert_spot(export_ctx, b_light, matrix_world, color, profile=None):
    data = b_light.data
    if data.shadow_soft_size > 0.0 or profile is not None:
        light = _cycles_light(export_ctx, b_light, matrix_world, color,
                              profile)
        # Blender spot lights emit along their local -Z axis
        axis = (export_ctx.axis_mat @ matrix_world).to_3x3() \
            @ Vector((0.0, 0.0, -1.0))
        light['dir'] = list(axis.normalized())
        light['angle'] = math.degrees(data.spot_size)
        light['blend'] = data.spot_blend
        return light
    # Blender spot lights point along -Z, Mitsuba's along +Z
    flip = Matrix.Rotation(math.pi, 4, 'X')
    return {
        'type': 'spot',
        'intensity': export_ctx.spectrum(
            _colored(power_to_intensity(data.energy), color)),
        'cutoff_angle': math.degrees(data.spot_size / 2.0),
        'beam_width': math.degrees(
            spot_beam_width(data.spot_size, data.spot_blend)),
        'to_world': export_ctx.transform_matrix(matrix_world @ flip),
    }


def _convert_sun(export_ctx, b_light, matrix_world, color):
    data = b_light.data
    if data.angle > 0.0:
        export_ctx.log(f'Light "{b_light.name_full}": Mitsuba directional '
                       'emitters have no angular diameter. Ignoring the sun '
                       'angle.', 'INFO')
    # Blender sun lights shine along -Z, Mitsuba's along +Z
    flip = Matrix.Rotation(math.pi, 4, 'X')
    # Mitsuba's directional emitter does not normalize the direction it
    # reads from `to_world`, so any object scale would scale the
    # irradiance. Cycles only uses the orientation of a sun light.
    orientation = (matrix_world @ flip).to_3x3().normalized().to_4x4()
    return {
        'type': 'directional',
        # The energy of a Blender sun light is its irradiance in W/m^2
        'irradiance': export_ctx.spectrum(_colored(data.energy, color)),
        'to_world': export_ctx.transform_matrix(orientation),
    }


def _convert_area(export_ctx, b_light, matrix_world, color):
    data = b_light.data
    obj_scale = matrix_world.to_scale()
    sx, sy = abs(obj_scale.x), abs(obj_scale.y)
    size_x = data.size
    if data.shape in ('SQUARE', 'DISK'):
        size_y = data.size
    elif data.shape in ('RECTANGLE', 'ELLIPSE'):
        size_y = data.size_y
    else:
        raise ConversionError(f'area light shape {data.shape} is not '
                              'supported')
    if data.shape in ('SQUARE', 'RECTANGLE'):
        shape = 'rectangle'
        area = (size_x * sx) * (size_y * sy)
    else:
        shape = 'disk'
        # The sizes are the diameters of the ellipse
        area = math.pi / 4.0 * (size_x * sx) * (size_y * sy)
    if area == 0.0:
        raise ConversionError('the area light is degenerate')
    if data.spread < math.pi - 1e-5:
        export_ctx.log(f'Light "{b_light.name_full}" has a spread angle, '
                       'which Mitsuba does not support. Ignoring it.', 'WARN')

    # Mitsuba rectangles and disks span [-1, 1] locally
    local = Matrix.Diagonal((size_x / 2.0, size_y / 2.0, 1.0)).to_4x4()
    radiance = _colored(power_to_radiance(data.energy, area), color)
    # Cycles area lights emit from their front side only and never occlude:
    # shadow rays ignore them, and other rays collect their emission and
    # continue. A one-sided emitter on a null BSDF behaves the same way.
    return {
        'type': shape,
        # Blender area lights emit along -Z, Mitsuba shapes along +Z
        'flip_normals': True,
        'to_world': export_ctx.transform_matrix(matrix_world @ local),
        'emitter': {
            'type': 'area',
            'radiance': export_ctx.spectrum(radiance),
        },
        'bsdf': {'type': 'null'},
    }


def is_portal(b_light):
    '''Whether a Blender light is a Cycles light portal: an area light that
    emits nothing and only guides the sampling of the world background.'''
    cycles = getattr(b_light.data, 'cycles', None)
    return b_light.data.type == 'AREA' and \
        bool(getattr(cycles, 'is_portal', False))


def _convert_portal(export_ctx, b_light, matrix_world):
    data = b_light.data
    size_x = data.size
    if data.shape in ('SQUARE', 'DISK'):
        size_y = data.size
    elif data.shape in ('RECTANGLE', 'ELLIPSE'):
        size_y = data.size_y
    else:
        raise ConversionError(f'area light shape {data.shape} is not '
                              'supported')
    if data.shape in ('DISK', 'ELLIPSE'):
        # Mitsuba portals are rectangular. The enclosing rectangle covers
        # the same opening, since portals only guide the sampling.
        export_ctx.log(f'Portal "{b_light.name_full}" is elliptic. '
                       'Exporting its bounding rectangle.', 'INFO')
    obj_scale = matrix_world.to_scale()
    if size_x * obj_scale.x * size_y * obj_scale.y == 0.0:
        raise ConversionError('the portal is degenerate')

    # Mitsuba portals are emitters spanning [-1, 1] locally and facing +Z,
    # Blender area lights face -Z
    local = Matrix.Diagonal((size_x / 2.0, size_y / 2.0, 1.0)).to_4x4()
    flip = Matrix.Rotation(math.pi, 4, 'X')
    return {
        'type': 'portal',
        'to_world': export_ctx.transform_matrix(matrix_world @ flip @ local),
    }


_converters = {
    'POINT': _convert_point,
    'SPOT': _convert_spot,
    'SUN': _convert_sun,
    'AREA': _convert_area,
}


# Emitters that no ray can intersect. Mitsuba rejects a visibility property
# on them, and cameras never see them anyway.
_delta_emitters = ('point', 'spot', 'directional')


def convert_light(export_ctx, b_light, matrix_world=None):
    '''Convert a Blender light object into a Mitsuba plugin dict. Returns
    None for a light that contributes nothing to the render. Raises
    ConversionError for unsupported lights.'''
    if matrix_world is None:
        matrix_world = b_light.matrix_world
    if is_portal(b_light):
        return _convert_portal(export_ctx, b_light, matrix_world)
    converter = _converters.get(b_light.data.type)
    if converter is None:
        raise ConversionError(f'light type {b_light.data.type} is not '
                              'supported')
    if b_light.data.energy == 0.0:
        export_ctx.log(f'Light "{b_light.name_full}" has zero power. '
                       'Skipping it.', 'INFO')
        return None
    visibility = ray_visibility(b_light, True)
    if visibility is None:
        export_ctx.log(f'Light "{b_light.name_full}" is hidden from every '
                       'ray type. Skipping it.', 'INFO')
        return None
    # Only the cycles_lights shape evaluates IES profiles per direction
    ies = [] if b_light.data.type in ('POINT', 'SPOT') else None
    factor = light_node_factor(export_ctx, b_light, matrix_world, ies)
    color = [c * f for c, f in zip(b_light.data.color, factor)]
    if max(color) <= 0.0:
        export_ctx.log(f'Light "{b_light.name_full}" emits nothing through its '
                       'node tree. Skipping it.', 'INFO')
        return None
    if ies:
        emitter = converter(export_ctx, b_light, matrix_world, color, ies[0])
    else:
        emitter = converter(export_ctx, b_light, matrix_world, color)

    if emitter['type'] in _delta_emitters:
        if visibility == 'primary':
            export_ctx.log(f'Light "{b_light.name_full}" is only visible '
                           'to camera rays. Skipping it.', 'INFO')
            return None
    elif visibility != 'all':
        # The light is a shape carrying an area emitter, and the shape owns
        # the visibility
        emitter['visibility'] = visibility
    return emitter


def export_light(export_ctx, light_instance):
    '''Convert a depsgraph light instance and add it to the scene dict.
    Never raises: failures produce a warning and the light is skipped.'''
    b_light = light_instance.object
    try:
        params = convert_light(export_ctx, b_light,
                               light_instance.matrix_world.copy())
    except Exception as e:
        export_ctx.log(f'Failed to export light "{b_light.name_full}": {e}. '
                       'Skipping it.', 'WARN')
        return
    if params is None:
        return
    if params['type'] == 'cycles_lights':
        export_ctx.add_cycles_light(params)
        return
    if export_ctx.export_ids:
        prefix = 'portal' if params['type'] == 'portal' else 'emit'
        export_ctx.data_add(params, name=f'{prefix}-{b_light.name_full}')
    else:
        export_ctx.data_add(params)
