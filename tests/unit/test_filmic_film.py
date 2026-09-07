"""The filmic post-processing plugin and the export of Blender's view
settings. The plugin is compared against images that Blender writes with
the same settings."""

import os
import sys

import bpy
import numpy as np
import pytest


def _variants():
    import mitsuba as mi
    return [v for v in ('llvm_ad_rgb', 'cuda_ad_rgb') if v in mi.variants()]


def _activate(mi_addon, variant):
    """Activates a Mitsuba variant and registers the addon plugins for it."""
    import mitsuba as mi
    mi.set_variant(variant)
    sys.modules[mi_addon].plugins.register_plugins()


@pytest.fixture(params=_variants())
def variant(request, mi_addon):
    _activate(mi_addon, request.param)
    return request.param


def _read_image(path):
    """The display-encoded values of an 8- or 16-bit image, without
    decoding."""
    import mitsuba as mi
    values = np.array(mi.Bitmap(path))
    return values.astype(np.float32) / np.iinfo(values.dtype).max


def _encode(linear):
    """The sRGB transfer function that the film applies to 8-bit output."""
    x = np.clip(linear, 0.0, 1.0)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * x ** (1 / 2.4) - 0.055)


def _load_stage(params, **extra):
    import mitsuba as mi
    stage = {'type': 'filmic'}
    stage.update(params)
    stage.update(extra)
    return mi.load_dict(stage)


def _set_view(scene, view, look, exposure, gamma, curves):
    vs = scene.view_settings
    vs.view_transform = view
    vs.look = look
    vs.exposure = exposure
    vs.gamma = gamma
    vs.use_curve_mapping = curves
    if curves:
        cm = vs.curve_mapping
        cm.curves[3].points.new(0.25, 0.1)
        cm.curves[3].points.new(0.75, 0.9)
        cm.curves[0].points.new(0.5, 0.8)
        cm.update()


def _blender_display(scene, linear, path):
    """Blender's display-encoded output for a linear image, written through
    the scene's view settings."""
    h, w, _ = linear.shape
    image = bpy.data.images.new('Linear', w, h, float_buffer=True)
    rgba = np.ones((h, w, 4), dtype=np.float32)
    rgba[..., :3] = linear
    # Blender stores images bottom-up
    image.pixels.foreach_set(rgba[::-1].ravel())
    settings = scene.render.image_settings
    settings.file_format = 'PNG'
    settings.color_depth = '16'
    settings.color_mode = 'RGB'
    image.save_render(path, scene=scene)
    bpy.data.images.remove(image)
    return _read_image(path)


VIEWS = [
    ('Standard', 'None', 0.0, 1.0, False),
    ('Filmic', 'None', 0.0, 1.0, False),
    ('Filmic', 'Very Low Contrast', -1.0, 1.2, True),
    ('Filmic', 'Low Contrast', 0.0, 1.0, False),
    ('Filmic', 'Medium Low Contrast', 0.0, 1.0, False),
    ('Filmic', 'Medium Contrast', 0.0, 1.0, False),
    ('Filmic', 'Medium High Contrast', 0.0, 1.0, False),
    ('Filmic', 'High Contrast', 1.5, 0.8, False),
    ('Filmic', 'Very High Contrast', 0.0, 1.0, False),
]


@pytest.mark.parametrize('view, look, exposure, gamma, curves', VIEWS)
def test_matches_blender_output(variant, fresh_scene, tmp_path, view, look,
                                exposure, gamma, curves):
    """The exported view settings and the plugin reproduce Blender's own
    display pipeline."""
    import mitsuba as mi
    from bl_ext.user_default.mitsuba_blender.convert.export.camera import \
        convert_view_settings
    from bl_ext.user_default.mitsuba_blender.io.exporter.export_context import \
        ExportContext

    _set_view(fresh_scene, view, look, exposure, gamma, curves)
    rng = np.random.default_rng(0)
    if look == 'None':
        linear = np.exp(rng.uniform(np.log(1e-4), np.log(50), (48, 64, 3)))
    else:
        # Blender returns to scene-linear values after a look, which sends
        # colors through the Filmic desaturation a second time and lifts
        # the dark channels of bright saturated colors. The plugin does not
        # reproduce this, and colors of moderate saturation are unaffected.
        linear = np.exp(rng.uniform(np.log(1e-4), np.log(50), (48, 64, 1))) * \
            rng.uniform(0.5, 1.0, (48, 64, 3))
    linear = linear.astype(np.float32)
    ref = _blender_display(fresh_scene, linear, str(tmp_path / 'ref.png'))

    ctx = ExportContext()
    ctx.directory = str(tmp_path)
    params = convert_view_settings(ctx, fresh_scene)
    assert not ctx.warnings
    mi.file_resolver().append(str(tmp_path))
    out = _encode(np.array(_load_stage(params).eval(mi.TensorXf(linear), ['R', 'G', 'B'])))
    error = np.abs(out - ref) * 255
    if view == 'Standard':
        assert error.max() < 0.05
    elif look == 'None':
        # Blender's coarse 3D table smooths the onset of the desaturation,
        # which shows in the dark channels of bright saturated colors
        assert error.max() < 5.0 and error.mean() < 0.5
    else:
        # The contrast curve is an analytic fit of Blender's tables
        assert error.max() < 1.5 and error.mean() < 0.3


def test_channel_selection(variant):
    """The leading color channels are transformed, the others pass
    through."""
    import mitsuba as mi
    rng = np.random.default_rng(1)
    image = rng.uniform(0.0, 2.0, (4, 6, 5)).astype(np.float32)
    stage = _load_stage({'contrast': 0.99}, exposure=1.0)

    out = np.array(stage.eval(mi.TensorXf(image), ['R', 'G', 'B', 'A', 'depth']))
    assert np.array_equal(out[..., 3:], image[..., 3:])
    assert np.all((out[..., :3] >= 0) & (out[..., :3] <= 1))
    # Without names, the first three channels are the color channels
    assert np.array_equal(np.array(stage.eval(image)), out)

    with pytest.raises(ValueError, match='R, G, B'):
        stage.eval(mi.TensorXf(image[..., :3]), ['X', 'Y', 'Z'])
    with pytest.raises(ValueError, match='R, G, B'):
        stage.eval(mi.TensorXf(image[..., :2]), ['Y', 'A'])


def test_film_output(variant, tmp_path):
    """The film's output is the stage's output, the linear image stays
    available and 8-bit files are sRGB-encoded."""
    import mitsuba as mi
    film = {'type': 'hdrfilm', 'width': 4, 'height': 3, 'pixel_format': 'rgba',
            'view': {'type': 'filmic', 'exposure': 1.5, 'gamma': 0.7, 'contrast': 1.2}}
    scene = mi.load_dict({
        'type': 'scene',
        'integrator': {'type': 'path', 'max_depth': 2},
        'emitter': {'type': 'constant', 'radiance': {'type': 'rgb', 'value': [0.5, 0.2, 2.0]}},
        'sensor': {
            'type': 'perspective',
            'film': film,
            'sampler': {'type': 'independent', 'sample_count': 4},
        },
    })
    image = np.array(mi.render(scene, spp=4))
    film = scene.sensors()[0].film()
    assert len(film.postprocess()) == 1
    linear = np.array(film.develop(postprocess=False))
    assert linear.shape == (3, 4, 4)
    assert np.allclose(linear[..., :3], [0.5, 0.2, 2.0], atol=1e-3)
    assert np.allclose(linear[..., 3], 1.0)

    channels = ['R', 'G', 'B', 'A']
    expected = np.array(film.postprocess()[0].eval(mi.TensorXf(linear), channels))
    assert np.allclose(image, expected, atol=1e-6)
    assert np.allclose(np.array(film.apply_postprocess(mi.TensorXf(linear), channels)),
                       expected, atol=1e-6)
    assert np.allclose(np.array(film.bitmap()), expected, atol=1e-6)
    assert np.allclose(np.array(film.bitmap(postprocess=False)), linear, atol=1e-6)

    # The film sRGB-encodes the stage's output; the 8-bit conversion
    # dithers by up to one step
    png = str(tmp_path / 'out.png')
    film.write(png)
    assert np.abs(_read_image(png) - _encode(expected)).max() <= 1.5 / 255

    exr = str(tmp_path / 'out.exr')
    film.write(exr)
    assert np.allclose(np.array(mi.Bitmap(exr)), expected, atol=1e-3)
    film.bitmap(postprocess=False).write(exr)
    assert np.allclose(np.array(mi.Bitmap(exr)), linear, atol=1e-3)


def test_requires_jit_variant(mi_addon):
    import mitsuba as mi
    _activate(mi_addon, 'scalar_rgb')
    with pytest.raises(RuntimeError, match='JIT variant'):
        _load_stage({})


def test_invalid_parameters(variant, tmp_path):
    from bl_ext.user_default.mitsuba_blender.convert import filmic
    with pytest.raises(RuntimeError, match='view transform'):
        _load_stage({'view_transform': 'AgX'})
    with pytest.raises(RuntimeError, match='contrast'):
        _load_stage({'contrast': 0.0})
    with pytest.raises(RuntimeError, match='gamma'):
        _load_stage({'gamma': -1.0})
    row = str(tmp_path / 'row.exr')
    filmic.write_table(row, np.zeros((1, 33)))
    with pytest.raises(RuntimeError, match='RGB'):
        _load_stage({'view_curves': row})
    with pytest.raises(RuntimeError, match='unreferenced'):
        _load_stage({'view_transform': 'Standard', 'typo': 1})


# Exporter

def _export_sensor(directory):
    from bl_ext.user_default.mitsuba_blender.io.exporter import SceneConverter
    converter = SceneConverter(render=False)
    converter.export_ctx.directory = str(directory)
    converter.scene_to_dict(bpy.context.evaluated_depsgraph_get())
    sensors = [v for v in converter.export_ctx.scene_data.values()
               if isinstance(v, dict) and v.get('type') == 'perspective']
    assert len(sensors) == 1
    return sensors[0], converter.export_ctx


def test_export_view_settings(mi_addon, fresh_scene, tmp_path):
    vs = fresh_scene.view_settings
    vs.view_transform = 'Filmic'
    vs.look = 'High Contrast'
    vs.exposure = 1.25
    vs.gamma = 0.8
    sensor, ctx = _export_sensor(tmp_path)
    film = sensor['film']
    assert film['type'] == 'hdrfilm'
    stage = film['postprocess']
    assert stage['type'] == 'filmic'
    assert stage['view_transform'] == 'Filmic'
    assert stage['contrast'] == pytest.approx(0.99)
    assert stage['exposure'] == pytest.approx(1.25)
    assert stage['gamma'] == pytest.approx(0.8)
    assert 'view_curves' not in stage
    assert not ctx.warnings
    assert not (tmp_path / 'luts').exists()

    # Without a look, the stage uses the contrast of the view's base curve
    vs.look = 'None'
    sensor, _ = _export_sensor(tmp_path)
    assert 'contrast' not in sensor['film']['postprocess']

    vs.look = 'High Contrast'
    vs.view_transform = 'Standard'
    sensor, _ = _export_sensor(tmp_path)
    stage = sensor['film']['postprocess']
    assert stage['view_transform'] == 'Standard'
    assert not any(key in stage for key in ('contrast', 'view_curves'))


def test_export_option_off(mi_addon, fresh_scene, tmp_path):
    from bl_ext.user_default.mitsuba_blender.io.exporter import SceneConverter
    converter = SceneConverter(render=False)
    converter.export_ctx.directory = str(tmp_path)
    converter.export_ctx.bake_display_transform = False
    converter.scene_to_dict(bpy.context.evaluated_depsgraph_get())
    films = [v['film'] for v in converter.export_ctx.scene_data.values()
             if isinstance(v, dict) and v.get('type') == 'perspective']
    assert films[0]['type'] == 'hdrfilm'
    assert 'postprocess' not in films[0]

    # Rendering inside Blender leaves the display transform to Blender
    assert SceneConverter(render=True).export_ctx.bake_display_transform is False


def test_export_unsupported_view_falls_back(mi_addon, fresh_scene, tmp_path):
    vs = fresh_scene.view_settings
    vs.view_transform = 'AgX'
    vs.look = 'AgX - Punchy'
    sensor, ctx = _export_sensor(tmp_path)
    stage = sensor['film']['postprocess']
    assert stage['view_transform'] == 'Standard'
    assert 'look' not in stage
    assert any('AgX' in w for w in ctx.warnings)


def test_export_view_curves(mi_addon, fresh_scene, tmp_path):
    import mitsuba as mi
    vs = fresh_scene.view_settings
    vs.view_transform = 'Standard'
    vs.use_curve_mapping = True
    cm = vs.curve_mapping
    cm.curves[3].points.new(0.25, 0.1)
    cm.curves[3].points.new(0.75, 0.9)
    cm.curves[0].points.new(0.5, 0.8)
    cm.update()
    sensor, ctx = _export_sensor(tmp_path)
    stage = sensor['film']['postprocess']
    assert stage['view_curves'] == 'luts/view_curves.exr'
    assert os.listdir(tmp_path / 'luts') == ['view_curves.exr']
    table = mi.Bitmap(str(tmp_path / 'luts' / 'view_curves.exr'))
    assert list(table.size()) == [259, 1] and table.channel_count() == 3
    assert table.metadata()['domain_min'] == pytest.approx(-1 / 256)
    assert table.metadata()['domain_max'] == pytest.approx(1 + 1 / 256)
