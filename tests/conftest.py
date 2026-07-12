"""Shared fixtures for the pytest-in-Blender suite (see tests/README.md)."""

import os
import sys

import bpy
import numpy as np
import pytest

ADDON_NAME = 'mitsuba-blender'
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

# Legacy tests predate this harness and need scripts/run_tests.py; hide them
# from the new runner (tests/_bootstrap.py sets this variable).
if os.environ.get('MI_BLENDER_TEST_HARNESS'):
    collect_ignore = [
        'test_addon.py',
        'test_compare.py',
        'test_importer.py',
        'test_mitsuba.py',
    ]


def pytest_configure(config):
    config.addinivalue_line(
        'markers', 'slow: takes more than a few seconds, skipped by default')
    config.addinivalue_line(
        'markers', 'packaging: builds/installs the extension zip, skipped by default')


@pytest.fixture(scope='session')
def mi_addon():
    """Registers the in-repo addon inside Blender for the whole session."""
    src = os.path.join(REPO_ROOT, ADDON_NAME)
    addons_dir = bpy.utils.user_resource('SCRIPTS', path='addons', create=True)
    link = os.path.join(addons_dir, ADDON_NAME)

    if os.path.lexists(link):
        os.remove(link)
    if sys.platform == 'win32':
        import _winapi
        _winapi.CreateJunction(src, link)
    else:
        os.symlink(src, link, target_is_directory=True)
    bpy.utils.refresh_script_paths()

    try:
        if bpy.ops.preferences.addon_enable(module=ADDON_NAME) != {'FINISHED'}:
            pytest.fail(f'Cannot enable the {ADDON_NAME} addon')
        prefs = bpy.context.preferences.addons[ADDON_NAME].preferences
        if not prefs.is_mitsuba_initialized:
            pytest.fail('Addon failed to initialize Mitsuba: '
                        f'{prefs.mitsuba_dependencies_status_message}')
        yield ADDON_NAME
        bpy.ops.preferences.addon_disable(module=ADDON_NAME)
    finally:
        os.remove(link)


@pytest.fixture
def fresh_scene():
    """Resets Blender to the factory startup scene."""
    bpy.ops.wm.read_homefile()
    return bpy.context.scene


@pytest.fixture(scope='session')
def render_dict():
    """Loads a Mitsuba scene dict and renders it, returning a numpy array."""
    import mitsuba as mi

    def _render(scene_dict, spp=4, seed=0):
        mi.set_variant('scalar_rgb')
        scene = mi.load_dict(scene_dict)
        return np.array(mi.render(scene, spp=spp, seed=seed))

    return _render


@pytest.fixture(scope='session')
def compare_images():
    """Asserts that two images match in mean value and RMSE."""

    def _compare(img, ref, mean_tol=0.01, rmse_tol=0.05):
        img = np.asarray(img, dtype=np.float64)
        ref = np.asarray(ref, dtype=np.float64)
        assert img.shape == ref.shape, \
            f'image shape {img.shape} != reference shape {ref.shape}'
        diff = img - ref
        mean_err = float(np.abs(diff.mean()))
        rmse = float(np.sqrt(np.mean(diff ** 2)))
        assert mean_err <= mean_tol, \
            f'mean error {mean_err:.6f} exceeds tolerance {mean_tol}'
        assert rmse <= rmse_tol, \
            f'RMSE {rmse:.6f} exceeds tolerance {rmse_tol}'

    return _compare
