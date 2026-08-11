import tempfile
import threading

import bpy
import numpy as np
import shutil
import tempfile
from ..io.exporter import SceneConverter


_texture_cache_dir = None
_texture_cache = {}


def get_texture_cache():
    """Directory and index of textures written for F12 renders, kept
    across renders so repeated F12 does not rewrite every image. Not
    used by XML export, which writes into the user's directory."""
    global _texture_cache_dir
    if _texture_cache_dir is None:
        _texture_cache_dir = tempfile.mkdtemp(prefix='mitsuba-blender-')
    return _texture_cache_dir, _texture_cache

def clear_texture_cache():
    global _texture_cache_dir
    if _texture_cache_dir is not None:
        shutil.rmtree(_texture_cache_dir, ignore_errors=True)
        _texture_cache_dir = None
    _texture_cache.clear()


def _make_progress_appender():
    '''Create a Mitsuba log appender that records the latest render
    progress fraction. Mitsuba reports progress through its logging API.'''
    import mitsuba as mi

    class ProgressAppender(mi.Appender):
        def __init__(self):
            super().__init__()
            self.fraction = 0.0

        def append(self, level, text):
            pass

        def log_progress(self, progress, name, formatted, eta, ptr=None):
            self.fraction = progress

    return ProgressAppender()


def run_render(integrator, scene, sensor, test_break, update_progress,
               poll_interval=0.1):
    '''Render a scene on a worker thread while the calling thread polls
    test_break and forwards render progress to update_progress.

    Returns True when the render was canceled. Mitsuba stops at the next
    block or iteration boundary after Integrator.cancel(), so the film
    then holds the partial image accumulated up to that point.
    '''
    import mitsuba as mi

    logger = mi.logger()
    appender = _make_progress_appender()
    old_level = logger.log_level()
    if old_level > mi.LogLevel.Info:
        # Progress records only reach appenders at Info level and below
        logger.set_log_level(mi.LogLevel.Info)
    logger.add_appender(appender)

    errors = []

    def work():
        try:
            integrator.render(scene, sensor)
        except Exception as e:
            errors.append(e)

    worker = threading.Thread(target=work, name='mitsuba-render')
    canceled = False
    try:
        worker.start()
        while worker.is_alive():
            worker.join(poll_interval)
            if not canceled and test_break():
                integrator.cancel()
                canceled = True
            update_progress(appender.fraction)
    finally:
        if worker.is_alive():
            integrator.cancel()
        worker.join()
        logger.remove_appender(appender)
        logger.set_log_level(old_level)

    if errors:
        raise errors[0]
    return canceled


class MitsubaRenderEngine(bpy.types.RenderEngine):

    bl_idname = "MITSUBA"
    bl_label = "Mitsuba"
    bl_use_preview = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.converter = SceneConverter(render=True)

    # This is the method called by Blender for both final renders (F12) and
    # small preview for materials, world and lights.
    def render(self, depsgraph):
        from mitsuba import set_variant
        b_scene = depsgraph.scene
        set_variant(b_scene.mitsuba.variant)
        from ..plugins import register_plugins
        register_plugins()

        scale = b_scene.render.resolution_percentage / 100.0
        self.size_x = int(b_scene.render.resolution_x * scale)
        self.size_y = int(b_scene.render.resolution_y * scale)

        # Temporary files (meshes, textures) written during the export must
        # survive until the scene has been loaded.
        export_dir, cache = get_texture_cache()
        self.converter.export_ctx.directory = export_dir
        self.converter.export_ctx.exported_images = cache
        self.converter.export_ctx.blender_triangulation = b_scene.mitsuba.blender_triangulation
        self.converter.scene_to_dict(depsgraph)
        mts_scene = self.converter.dict_to_scene()

        sensor = mts_scene.sensors()[0]
        self.update_stats('', 'Rendering with Mitsuba')
        canceled = run_render(mts_scene.integrator(), mts_scene, sensor,
                              self.test_break, self.update_progress)
        if canceled:
            self.report({'WARNING'}, 'Render canceled')

        self._write_render_result(sensor.film())

        warnings = self.converter.export_ctx.warnings
        if warnings:
            self.error_set(f'{len(warnings)} warning(s) during the scene '
                           'export (see the console)')

    def _write_render_result(self, film):
        '''Split the film into its image and AOV components and write them
        to the render result. Pixel values are passed through unchanged:
        Blender expects linear data in its render passes.'''
        results = [(name, _pass_channels(bitmap), np.atleast_3d(bitmap))
                   for name, bitmap in film.bitmap().split()]

        # All passes must be declared before begin_result
        for name, channels, pixels in results:
            if name == '<root>':
                # The root image goes to the built-in Combined pass
                continue
            self.add_pass(name, len(channels), ''.join(channels))

        blender_result = self.begin_result(0, 0, self.size_x, self.size_y)
        layer = blender_result.layers[0]

        for name, channels, pixels in results:
            if name == '<root>':
                name = 'Combined'
                pixels = _to_rgba(pixels)
            elif pixels.shape[2] < len(channels):
                # Zero padding for channel counts Blender does not support
                padding = np.zeros((*pixels.shape[:2],
                                    len(channels) - pixels.shape[2]))
                pixels = np.dstack((pixels, padding))
            layer.passes[name].rect = np.flip(pixels, 0).reshape((self.size_x * self.size_y, -1))
        self.end_result(blender_result)


def _to_rgba(pixels):
    '''Blender's Combined pass is always RGBA. Monochrome films replicate
    their single luminance channel; a missing alpha channel is filled with
    ones. Writing a rect with fewer than four channels crashes Blender.'''
    if pixels.shape[2] in (1, 2):
        luminance = np.repeat(pixels[:, :, :1], 3, axis=2)
        pixels = np.dstack((luminance, pixels[:, :, 1:]))
    if pixels.shape[2] == 3:
        pixels = np.dstack((pixels, np.ones((*pixels.shape[:2], 1))))
    return pixels


def _pass_channels(bitmap):
    '''The per-channel identifiers to declare for a film component.
    Two-channel outputs (e.g. UV coordinates) are padded to three since
    Blender only supports 1, 3 or 4 channels per pass.'''
    channels = [f.name.split('.')[-1] for f in bitmap.struct_()]
    if len(channels) == 2:
        channels.append(next(c for c in 'AZWQ' if c not in channels))
    return channels
