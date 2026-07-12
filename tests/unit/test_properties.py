"""Round trips through the hand-written render/camera property groups."""

import importlib

import bpy
import pytest


def export_scene_dict(addon_module, tmp_path):
    exporter = importlib.import_module(f'{addon_module}.io.exporter')
    converter = exporter.SceneConverter(render=True)
    converter.export_ctx.directory = str(tmp_path)
    converter.scene_to_dict(bpy.context.evaluated_depsgraph_get())
    return converter.export_ctx.scene_data


def find_by_type(scene_dict, plugin_type):
    return [v for v in scene_dict.values()
            if isinstance(v, dict) and v.get('type') == plugin_type]


def test_integrator_settings_round_trip(mi_addon, fresh_scene, tmp_path):
    scene = fresh_scene
    scene.render.engine = 'MITSUBA'
    scene.mitsuba.active_integrator = 'volpath'
    props = scene.mitsuba.available_integrators.volpath
    props.max_depth = 12
    props.rr_depth = 3
    props.hide_emitters = True

    scene_dict = export_scene_dict(mi_addon, tmp_path)
    integrators = find_by_type(scene_dict, 'volpath')
    assert len(integrators) == 1
    assert integrators[0] == {
        'type': 'volpath',
        'max_depth': 12,
        'rr_depth': 3,
        'hide_emitters': True,
    }


def test_sampler_and_rfilter_round_trip(mi_addon, fresh_scene, tmp_path):
    scene = fresh_scene
    scene.render.engine = 'MITSUBA'
    camera_settings = scene.camera.data.mitsuba
    camera_settings.active_sampler = 'stratified'
    camera_settings.samplers.stratified.sample_count = 64
    camera_settings.samplers.stratified.seed = 7
    camera_settings.samplers.stratified.jitter = False
    camera_settings.active_rfilter = 'gaussian'
    camera_settings.rfilters.gaussian.stddev = 0.8
    # Property changes do not tag the datablock, so the cached evaluated
    # copy in the depsgraph would still hold the old values.
    scene.camera.data.update_tag()

    scene_dict = export_scene_dict(mi_addon, tmp_path)
    sensors = find_by_type(scene_dict, 'perspective')
    assert len(sensors) == 1
    sensor = sensors[0]
    assert sensor['sampler'] == {
        'type': 'stratified',
        'sample_count': 64,
        'seed': 7,
        'jitter': False,
    }
    rfilter = sensor['film']['rfilter']
    assert rfilter['type'] == 'gaussian'
    assert rfilter['stddev'] == pytest.approx(0.8)


def test_custom_integrator_used_verbatim(mi_addon, fresh_scene, tmp_path):
    scene = fresh_scene
    scene.render.engine = 'MITSUBA'
    scene.mitsuba.active_integrator = 'path'
    scene.mitsuba.custom_integrator = \
        "{'type': 'stokes', 'nested': {'type': 'path', 'max_depth': 6}}"

    scene_dict = export_scene_dict(mi_addon, tmp_path)
    assert find_by_type(scene_dict, 'path') == []
    integrators = find_by_type(scene_dict, 'stokes')
    assert len(integrators) == 1
    assert integrators[0] == {
        'type': 'stokes',
        'nested': {'type': 'path', 'max_depth': 6},
    }


def test_custom_integrator_rejects_non_dict(mi_addon, fresh_scene):
    scene = fresh_scene
    scene.mitsuba.custom_integrator = "['not', 'a', 'dict']"
    with pytest.raises(ValueError):
        scene.mitsuba.integrator_to_dict()


def test_aov_integrator_dict(mi_addon, fresh_scene):
    scene = fresh_scene
    scene.mitsuba.active_integrator = 'aov'
    aov = scene.mitsuba.available_integrators.aov
    aov.depth = True
    aov.sh_normal = True
    aov.nested_integrator = 'volpath'
    aov.volpath.max_depth = 4

    result = scene.mitsuba.integrator_to_dict()
    assert result['type'] == 'aov'
    assert result['aovs'] == 'depth:depth,sh_normal:sh_normal'
    assert result['volpath']['type'] == 'volpath'
    assert result['volpath']['max_depth'] == 4

    import mitsuba as mi
    mi.set_variant('scalar_rgb')
    assert mi.load_dict(result) is not None


def test_import_preserves_unsupported_integrator(mi_addon, fresh_scene, tmp_path):
    # Integrators without a UI representation (e.g. moment) are stored in
    # the custom dict escape hatch so they survive a round trip.
    scene_file = tmp_path / 'scene.xml'
    scene_file.write_text('''
        <scene version="3.0.0">
            <integrator type="moment">
                <integrator type="path">
                    <integer name="max_depth" value="7"/>
                </integrator>
            </integrator>
        </scene>''')
    assert bpy.ops.import_scene.mitsuba(
        filepath=str(scene_file), import_render_settings=True) == {'FINISHED'}

    result = bpy.context.scene.mitsuba.integrator_to_dict()
    assert result['type'] == 'moment'
    nested = [v for v in result.values() if isinstance(v, dict)]
    assert nested == [{'type': 'path', 'max_depth': 7}]


ALL_INTEGRATORS = ['path', 'direct', 'volpath', 'volpathmis', 'ptracer']
ALL_SAMPLERS = ['independent', 'stratified', 'multijitter', 'orthogonal',
                'ldsampler']
ALL_RFILTERS = ['box', 'tent', 'gaussian', 'mitchell', 'catmullrom', 'lanczos']


@pytest.mark.parametrize('name', ALL_INTEGRATORS)
def test_integrator_dicts_load(mi_addon, fresh_scene, name):
    import mitsuba as mi
    mi.set_variant('scalar_rgb')
    scene = fresh_scene
    scene.mitsuba.active_integrator = name
    assert mi.load_dict(scene.mitsuba.integrator_to_dict()) is not None


@pytest.mark.parametrize('name', ALL_SAMPLERS)
def test_sampler_dicts_load(mi_addon, fresh_scene, name):
    import mitsuba as mi
    mi.set_variant('scalar_rgb')
    camera_settings = fresh_scene.camera.data.mitsuba
    camera_settings.active_sampler = name
    assert mi.load_dict(camera_settings.sampler_to_dict()) is not None


@pytest.mark.parametrize('name', ALL_RFILTERS)
def test_rfilter_dicts_load(mi_addon, fresh_scene, name):
    import mitsuba as mi
    mi.set_variant('scalar_rgb')
    camera_settings = fresh_scene.camera.data.mitsuba
    camera_settings.active_rfilter = name
    assert mi.load_dict(camera_settings.rfilter_to_dict()) is not None
