import tempfile
import threading

import bpy
import numpy as np
from ..io.exporter import SceneConverter


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

        scale = b_scene.render.resolution_percentage / 100.0
        self.size_x = int(b_scene.render.resolution_x * scale)
        self.size_y = int(b_scene.render.resolution_y * scale)

        # Temporary files (meshes, textures) written during the export must
        # survive until the scene has been loaded.
        with tempfile.TemporaryDirectory() as export_dir:
            self.converter.export_ctx.directory = export_dir
            self.converter.scene_to_dict(depsgraph)
            mts_scene = self.converter.dict_to_scene()

        sensor = mts_scene.sensors()[0]
        self.update_stats('', 'Rendering with Mitsuba')
        canceled = run_render(mts_scene.integrator(), mts_scene, sensor,
                              self.test_break, self.update_progress)
        if canceled:
            self.report({'WARNING'}, 'Render canceled')

        render_results = sensor.film().bitmap().split()

        for result in render_results:
            buf_name = result[0].replace("<root>", "Combined")
            if buf_name == 'Combined':
                # The root image goes to the built-in Combined pass
                continue
            channel_count = result[1].channel_count() if result[1].channel_count() != 2 else 3

            self.add_pass(buf_name, channel_count, ''.join([f.name.split('.')[-1] for f in result[1].struct_()]))

        blender_result = self.begin_result(0, 0, self.size_x, self.size_y)

        for result in render_results:
            render_pixels = np.array(result[1])
            if result[1].channel_count() == 2:
                # Add a dummy third channel
                render_pixels = np.dstack((render_pixels, np.zeros((*render_pixels.shape[:2], 1))))
            # Here we write the pixel values to the RenderResult
            buf_name = result[0].replace("<root>", "Combined")
            if buf_name == 'Combined' and render_pixels.shape[2] == 3:
                # Blender's Combined pass is always RGBA
                render_pixels = np.dstack((render_pixels, np.ones((*render_pixels.shape[:2], 1))))
            layer = blender_result.layers[0].passes[buf_name]
            layer.rect = np.flip(render_pixels, 0).reshape((self.size_x*self.size_y, -1))
        self.end_result(blender_result)
