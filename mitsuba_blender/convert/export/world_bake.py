'''Baking a Blender world that has no Mitsuba equivalent into an
environment map.

A world driven by a Sky Texture, a Mix Shader or any other procedural node
chain cannot be translated (see ``convert_world``), and dropping it costs the
scene its main light. Rendering it once with Cycles through an
equirectangular camera turns it into an ``envmap`` that lights the scene the
same way.
'''

import math
import os
import shutil
import tempfile

import bpy
from mathutils import Euler

from .materials.textures import export_image

# Rotation of the equirectangular bake camera: upright, then yawed a quarter
# turn, which lays the rendered image out in the same equirectangular
# parametrization as Blender's environment texture lookup. The baked emitter
# therefore takes the ``to_world`` of a translated environment texture.
BAKE_CAMERA_ROTATION = Euler((math.pi / 2, 0.0, -math.pi / 2))

# What a Light Path node reports to an indirect diffuse ray, the kind that
# lights the scene -- not to the camera ray the bake actually traces, nor the
# camera-ray values the material evaluator substitutes (_LIGHT_PATH_DEFAULTS
# in materials/_resolve.py). Freezing the outputs to these bakes the lighting
# branch of a world that switches on Is Camera Ray to show the camera a
# different backdrop.
LIGHTING_RAY_LIGHT_PATH = {
    'Is Camera Ray': 0.0,
    'Is Shadow Ray': 0.0,
    'Is Diffuse Ray': 1.0,
    'Is Glossy Ray': 0.0,
    'Is Singular Ray': 0.0,
    'Is Reflection Ray': 0.0,
    'Is Transmission Ray': 0.0,
    'Is Volume Scatter Ray': 0.0,
    'Ray Length': 0.0,
    'Ray Depth': 1.0,
    'Diffuse Depth': 1.0,
    'Glossy Depth': 0.0,
    'Transparent Depth': 0.0,
    'Transmission Depth': 0.0,
}


def _panorama_settings(b_camera_data):
    '''Where the panorama type lives: on the camera since Blender 4.3, on
    its Cycles settings before that.'''
    if hasattr(b_camera_data, 'panorama_type'):
        return b_camera_data
    return b_camera_data.cycles


def _has_light_path(b_tree, seen=None):
    '''Whether ``b_tree`` or a group it uses holds a Light Path node.'''
    seen = set() if seen is None else seen
    if b_tree is None or b_tree.as_pointer() in seen:
        return False
    seen.add(b_tree.as_pointer())
    return any(b_node.type == 'LIGHT_PATH'
               or (b_node.type == 'GROUP'
                   and _has_light_path(b_node.node_tree, seen))
               for b_node in b_tree.nodes)


def _set_constant(b_socket, value):
    '''Write ``value`` to a socket default, matching its component count.
    False when the socket takes no constant.'''
    default = getattr(b_socket, 'default_value', None)
    if default is None:
        return False
    try:
        count = len(default)
    except TypeError:
        b_socket.default_value = value
        return True
    b_socket.default_value = [value] * 3 + [1.0] if count == 4 \
        else [value] * count
    return True


def _freeze_light_path(export_ctx, b_tree, groups):
    '''Replace the Light Path outputs of ``b_tree`` by their values for a
    lighting ray. Groups holding one are copied into ``groups`` first, so
    the user's node groups stay untouched.'''
    for b_node in list(b_tree.nodes):
        if b_node.type == 'LIGHT_PATH':
            for b_output in b_node.outputs:
                value = LIGHTING_RAY_LIGHT_PATH.get(b_output.name)
                for link in list(b_output.links):
                    b_target = link.to_socket
                    b_tree.links.remove(link)
                    if value is None or not _set_constant(b_target, value):
                        export_ctx.log(
                            f'Light Path output "{b_output.name}" drives '
                            f'"{b_target.name}", which takes no constant; '
                            'the world bake leaves it at its default.',
                            'WARN')
        elif b_node.type == 'GROUP' and _has_light_path(b_node.node_tree):
            b_node.node_tree = b_node.node_tree.copy()
            groups.append(b_node.node_tree)
            _freeze_light_path(export_ctx, b_node.node_tree, groups)


def _bake_source(export_ctx, b_world):
    '''A copy of ``b_world`` to render, and the node groups copied along
    with it. The caller removes both.'''
    source = b_world.copy()
    groups = []
    if _has_light_path(source.node_tree):
        _freeze_light_path(export_ctx, source.node_tree, groups)
        export_ctx.log(f'The world "{b_world.name}" switches on Light Path; '
                       'it is baked with the values an indirect diffuse ray '
                       'sees.', 'INFO')
    return source, groups


def _render_equirectangular(b_world, resolution, filepath):
    '''Render ``b_world`` on its own to an equirectangular 32-bit EXR.'''
    b_scene = bpy.data.scenes.new('mitsuba_world_bake')
    b_camera_data = bpy.data.cameras.new('mitsuba_world_bake')
    b_camera = bpy.data.objects.new('mitsuba_world_bake', b_camera_data)
    try:
        b_scene.world = b_world
        b_scene.render.engine = 'CYCLES'
        b_scene.render.resolution_x = 2 * resolution
        b_scene.render.resolution_y = resolution
        b_scene.render.resolution_percentage = 100
        b_scene.render.film_transparent = False
        b_scene.render.filepath = filepath
        settings = b_scene.render.image_settings
        settings.file_format = 'OPEN_EXR'
        settings.color_depth = '32'
        settings.exr_codec = 'ZIP'
        # The map holds radiance, so the display transform must stay out of it
        b_scene.view_settings.view_transform = 'Standard'
        b_scene.view_settings.look = 'None'
        # One sample is exact: every pixel is a single environment lookup
        cycles = getattr(b_scene, 'cycles', None)
        if cycles is not None:
            cycles.samples = 1
            cycles.use_denoising = False
        b_camera_data.type = 'PANO'
        _panorama_settings(b_camera_data).panorama_type = 'EQUIRECTANGULAR'
        b_camera.rotation_euler = BAKE_CAMERA_ROTATION
        b_scene.collection.objects.link(b_camera)
        b_scene.camera = b_camera
        with bpy.context.temp_override(scene=b_scene):
            # The bake looks at the world along a camera ray, so a world the
            # user hid from camera rays would come out black. export_world
            # puts the ray visibility back on the emitter it builds.
            visibility = getattr(b_world, 'cycles_visibility', None)
            if visibility is not None:
                visibility.camera = True
            bpy.ops.render.render(write_still=True)
    finally:
        bpy.data.objects.remove(b_camera, do_unlink=True)
        bpy.data.cameras.remove(b_camera_data, do_unlink=True)
        bpy.data.scenes.remove(b_scene, do_unlink=True)


def bake_world(export_ctx, b_world):
    '''Bake ``b_world`` with Cycles and return a partial ``envmap`` emitter
    dict holding the image reference; the world exporter adds scale and
    to_world, as it does for an environment texture. The user's world
    datablock is not modified: the bake runs on a copy.'''
    resolution = max(int(export_ctx.bake_world_resolution), 2)
    directory = tempfile.mkdtemp(prefix='mitsuba_world_bake_')
    path = os.path.join(directory,
                        f'{bpy.path.clean_name(b_world.name)}_baked.exr')
    source, groups = _bake_source(export_ctx, b_world)
    try:
        _render_equirectangular(source, resolution, path)
        # Blender reads a 32-bit EXR as the linear data the bake wrote, so
        # the file only has to be moved into the export directory
        b_image = bpy.data.images.load(path)
        try:
            params = {'type': 'envmap'}
            params['filename'], _ = export_image(export_ctx, b_image)
        finally:
            bpy.data.images.remove(b_image)
    finally:
        bpy.data.worlds.remove(source, do_unlink=True)
        for b_tree in groups:
            bpy.data.node_groups.remove(b_tree, do_unlink=True)
        shutil.rmtree(directory, ignore_errors=True)
    return params
