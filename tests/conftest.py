"""Shared fixtures for the pytest-in-Blender suite (see tests/README.md)."""

import os
import sys

import bpy
import numpy as np
import pytest

ADDON_ID = 'mitsuba_blender'
ADDON_MODULE = f'bl_ext.user_default.{ADDON_ID}'
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

def pytest_addoption(parser):
    parser.addoption(
        '--update-refs', action='store_true', default=False,
        help='regenerate golden reference images instead of comparing')


def pytest_configure(config):
    config.addinivalue_line(
        'markers', 'slow: takes more than a few seconds, skipped by default')
    config.addinivalue_line(
        'markers', 'packaging: builds/installs the extension zip, skipped by default')


@pytest.fixture(scope='session')
def mi_addon():
    """Registers the in-repo extension inside Blender for the whole session."""
    src = os.path.join(REPO_ROOT, ADDON_ID)
    repo_dir = os.path.join(bpy.utils.user_resource('EXTENSIONS'), 'user_default')
    os.makedirs(repo_dir, exist_ok=True)
    link = os.path.join(repo_dir, ADDON_ID)

    if os.path.lexists(link):
        os.remove(link)
    if sys.platform == 'win32':
        import _winapi
        _winapi.CreateJunction(src, link)
    else:
        os.symlink(src, link, target_is_directory=True)
    bpy.ops.extensions.repo_refresh_all()

    try:
        if bpy.ops.preferences.addon_enable(module=ADDON_MODULE) != {'FINISHED'}:
            pytest.fail(f'Cannot enable the {ADDON_MODULE} extension')
        addon_module = sys.modules[ADDON_MODULE]
        if addon_module.mitsuba_version is None:
            pytest.fail('Extension failed to initialize Mitsuba: '
                        f'{addon_module.init_error}')
        yield ADDON_MODULE
        if ADDON_MODULE in bpy.context.preferences.addons:
            bpy.ops.preferences.addon_disable(module=ADDON_MODULE)
    finally:
        if os.path.lexists(link):
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
