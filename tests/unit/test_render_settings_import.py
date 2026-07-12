"""Render-settings import is opt-in and never touches the active render
engine or the Cycles settings."""

import os

import bpy
import pytest

SCENES = os.path.join(os.path.dirname(__file__), '..', 'res', 'scenes')


def _import(name, **kwargs):
    assert bpy.ops.import_scene.mitsuba(
        filepath=os.path.join(SCENES, name), **kwargs) == {'FINISHED'}
    return bpy.context.scene


def test_settings_not_applied_by_default(mi_addon, fresh_scene):
    engine_before = bpy.context.scene.render.engine
    res_before = (bpy.context.scene.render.resolution_x,
                  bpy.context.scene.render.resolution_y)

    scene = _import('film_hdrfilm.xml')

    assert scene.render.engine == engine_before
    assert (scene.render.resolution_x, scene.render.resolution_y) == \
        res_before
    # The integrator properties keep their defaults
    assert scene.mitsuba.available_integrators.path.max_depth == -1


def test_import_never_touches_engine_or_cycles(mi_addon, fresh_scene):
    engine_before = bpy.context.scene.render.engine
    cycles_before = (bpy.context.scene.cycles.samples,
                     bpy.context.scene.cycles.max_bounces,
                     bpy.context.scene.cycles.pixel_filter_type)

    scene = _import('test1.xml', import_render_settings=True)

    assert scene.render.engine == engine_before
    assert (scene.cycles.samples, scene.cycles.max_bounces,
            scene.cycles.pixel_filter_type) == cycles_before


def test_integrator_settings_applied(mi_addon, fresh_scene):
    scene = _import('integrator_path.xml', import_render_settings=True)

    assert scene.mitsuba.variant == 'scalar_rgb'
    assert scene.mitsuba.active_integrator == 'path'
    integrator = scene.mitsuba.available_integrators.path
    assert integrator.max_depth == 2
    assert integrator.rr_depth == 4
    assert integrator.hide_emitters


def test_sampler_settings_applied(mi_addon, fresh_scene):
    scene = _import('sampler_stratified.xml', import_render_settings=True)

    camera = scene.camera.data.mitsuba
    assert camera.active_sampler == 'stratified'
    assert camera.samplers.stratified.sample_count == 12
    assert camera.samplers.stratified.seed == 1
    assert not camera.samplers.stratified.jitter


def test_rfilter_settings_applied(mi_addon, fresh_scene):
    scene = _import('rfilter_gaussian.xml', import_render_settings=True)

    camera = scene.camera.data.mitsuba
    assert camera.active_rfilter == 'gaussian'
    assert camera.rfilters.gaussian.stddev == pytest.approx(1.5)


def test_film_settings_applied(mi_addon, fresh_scene):
    scene = _import('film_hdrfilm.xml', import_render_settings=True)

    assert scene.render.resolution_percentage == 100
    assert scene.render.resolution_x == 1280
    assert scene.render.resolution_y == 720
    assert scene.render.image_settings.file_format == 'OPEN_EXR'
    assert scene.render.image_settings.color_mode == 'RGBA'
    assert scene.render.image_settings.color_depth == '32'
    assert not scene.render.use_border


def test_film_crop_applied(mi_addon, fresh_scene):
    scene = _import('film_hdrfilm_crop.xml', import_render_settings=True)

    assert scene.render.use_border
    assert scene.render.border_min_x == pytest.approx(0.0)
    assert scene.render.border_min_y == pytest.approx(0.0)
    assert scene.render.border_max_x == pytest.approx(0.5)
    assert scene.render.border_max_y == pytest.approx(0.5)


def test_top_level_sampler_via_ref(mi_addon, fresh_scene, tmp_path):
    # A sampler declared at the scene level used to be converted from the
    # root pass before any camera exists, crashing on scene.camera.data
    import sys
    importer = sys.modules[mi_addon].io.importer
    from bl_ext.user_default.mitsuba_blender.io import bl_utils
    from bpy_extras.io_utils import axis_conversion

    scene_file = tmp_path / 'scene.xml'
    scene_file.write_text('''<scene version="3.0.0">
        <sampler type="stratified" id="samp">
            <integer name="sample_count" value="12"/>
        </sampler>
        <sensor type="perspective">
            <ref id="samp"/>
        </sensor>
    </scene>''')

    axis_mat = axis_conversion(to_forward='-Z', to_up='Y').to_4x4()
    scene = bl_utils.init_empty_scene(bpy.context, name='sampler-ref-test')
    warnings = importer.load_mitsuba_scene(
        bpy.context, scene, scene.collection, str(scene_file), axis_mat,
        False, True, import_render_settings=True)

    assert warnings == []
    camera = scene.camera.data.mitsuba
    assert camera.active_sampler == 'stratified'
    assert camera.samplers.stratified.sample_count == 12
