"""Worker-thread rendering: progress reporting and cancellation."""

import sys
import time

import bpy
import pytest


def _final_module(mi_addon):
    return sys.modules[mi_addon].engine.final


def _slow_scene(spp):
    """A scene whose render time scales with spp (about 5ms per spp unit
    at spp=1024 on a workstation)."""
    import mitsuba as mi
    mi.set_variant('scalar_rgb')
    return mi.load_dict({
        'type': 'scene',
        'integrator': {'type': 'path', 'max_depth': 16},
        'sensor': {
            'type': 'perspective',
            'film': {'type': 'hdrfilm', 'width': 512, 'height': 512},
            'sampler': {'type': 'independent', 'sample_count': spp},
        },
        'emitter': {'type': 'constant'},
        'shape': {'type': 'sphere', 'bsdf': {'type': 'dielectric'}},
    })


def test_progress_updates(mi_addon):
    final = _final_module(mi_addon)
    scene = _slow_scene(spp=1024)

    fractions = []
    canceled = final.run_render(
        scene.integrator(), scene, scene.sensors()[0],
        test_break=lambda: False, update_progress=fractions.append)

    assert not canceled
    assert fractions, 'the polling loop never reported progress'
    assert fractions == sorted(fractions), 'progress must be monotonic'
    assert 0.0 <= fractions[-1] <= 1.0
    assert max(fractions) > 0.2, 'progress never advanced'


def test_cancel_stops_render(mi_addon):
    final = _final_module(mi_addon)
    # A full render at this sample count takes more than a minute
    scene = _slow_scene(spp=16384)

    start = time.monotonic()
    canceled = final.run_render(
        scene.integrator(), scene, scene.sensors()[0],
        test_break=lambda: True, update_progress=lambda fraction: None)
    elapsed = time.monotonic() - start

    assert canceled
    assert elapsed < 20.0, f'cancellation took {elapsed:.1f}s'


def test_worker_exception_propagates(mi_addon):
    final = _final_module(mi_addon)

    class BrokenIntegrator:
        def render(self, scene, sensor):
            raise RuntimeError('worker failure')

        def cancel(self):
            pass

    with pytest.raises(RuntimeError, match='worker failure'):
        final.run_render(BrokenIntegrator(), None, None,
                         test_break=lambda: False,
                         update_progress=lambda fraction: None)


def test_f12_cancel_does_not_deadlock(mi_addon, fresh_scene):
    # RNA functions like test_break resolve before Python class attributes,
    # so the break signal is injected by wrapping run_render instead.
    final = _final_module(mi_addon)
    scene = fresh_scene
    scene.render.engine = 'MITSUBA'
    scene.mitsuba.variant = 'scalar_rgb'
    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    # Slow enough that a full render takes minutes
    scene.camera.data.mitsuba.samplers.independent.sample_count = 16384

    outcome = {}
    orig_run_render = final.run_render

    def breaking_run_render(integrator, mi_scene, sensor, test_break,
                            update_progress, **kwargs):
        assert callable(test_break) and callable(update_progress)
        outcome['canceled'] = orig_run_render(
            integrator, mi_scene, sensor, lambda: True, update_progress,
            **kwargs)
        return outcome['canceled']

    final.run_render = breaking_run_render
    try:
        start = time.monotonic()
        result = bpy.ops.render.render()
        elapsed = time.monotonic() - start
    finally:
        final.run_render = orig_run_render

    assert result == {'FINISHED'}
    assert outcome.get('canceled') is True
    assert elapsed < 45.0, f'canceled F12 render took {elapsed:.1f}s'
