'''Render smoke test across every UI-selectable Mitsuba variant.

The rest of the suite pins scalar_rgb; this exercises the same default-cube
F12 path once per variant offered by the variant dropdown, so a variant that
crashes or renders black is caught by CI.
'''

import bpy
import numpy as np
import pytest

import mitsuba


def _selectable_variants():
    return mitsuba.variants()


@pytest.fixture(autouse=True)
def _restore_variant():
    yield
    mitsuba.set_variant('scalar_rgb')


@pytest.mark.slow
@pytest.mark.parametrize('variant', _selectable_variants())
def test_f12_renders_in_variant(variant, mi_addon, fresh_scene, tmp_path):
    if 'cuda' in variant:
        pytest.skip('CUDA availability is machine-dependent')
    try:
        mitsuba.set_variant(variant)
    except (ImportError, AttributeError) as e:
        pytest.skip(f'variant {variant} unavailable: {e}')

    scene = fresh_scene
    scene.render.engine = 'MITSUBA'
    scene.mitsuba.variant = variant
    scene.render.resolution_x = 32
    scene.render.resolution_y = 32
    scene.render.filepath = str(tmp_path / f'{variant}.exr')
    scene.render.image_settings.file_format = 'OPEN_EXR'

    assert bpy.ops.render.render(write_still=True) == {'FINISHED'}

    render = bpy.data.images.load(scene.render.filepath)
    pixels = np.array(render.pixels[:]).reshape(-1, 4)
    assert np.all(np.isfinite(pixels))
    # The default cube under the default light is neither black nor uniform
    assert pixels[:, :3].max() > 0.01
    assert pixels[:, :3].std() > 1e-4
