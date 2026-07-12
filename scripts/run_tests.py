import argparse
import sys
import os

import bpy
import pytest

ADDON_ID = 'mitsuba_blender'
ADDON_MODULE = f'bl_ext.user_default.{ADDON_ID}'

class SetupPlugin:
    def __init__(self, custom_mitsuba_path: str | None = None):
        repo_root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        self.mi_addon_dir = os.path.join(repo_root, ADDON_ID)
        self.bl_repo_dir = os.path.join(
            bpy.utils.user_resource('EXTENSIONS'), 'user_default')
        self.bl_mi_addon_dir = os.path.join(self.bl_repo_dir, ADDON_ID)
        self.custom_mitsuba_path = custom_mitsuba_path

    def pytest_configure(self, config):
        os.makedirs(self.bl_repo_dir, exist_ok=True)
        if os.path.lexists(self.bl_mi_addon_dir):
            os.remove(self.bl_mi_addon_dir)

        # Create a symlink from the addon to the Blender extensions folder
        if sys.platform == 'win32':
            import _winapi
            _winapi.CreateJunction(str(self.mi_addon_dir), str(self.bl_mi_addon_dir))
        else:
            os.symlink(self.mi_addon_dir, self.bl_mi_addon_dir, target_is_directory=True)
        bpy.ops.extensions.repo_refresh_all()

        if self.custom_mitsuba_path:
            python_path = os.path.join(self.custom_mitsuba_path, 'python')
            if python_path not in sys.path:
                sys.path.insert(0, python_path)

        if bpy.ops.preferences.addon_enable(module=ADDON_MODULE) != {'FINISHED'}:
            raise RuntimeError('Cannot enable the mitsuba_blender extension')

        addon_module = sys.modules[ADDON_MODULE]
        if addon_module.mitsuba_version is None:
            raise RuntimeError(
                f'Failed to initialize Mitsuba library: {addon_module.init_error}')

    def pytest_unconfigure(self):
        # The session fixture in tests/conftest.py may already have disabled
        # the addon and removed the symlink.
        if ADDON_MODULE in bpy.context.preferences.addons:
            bpy.ops.preferences.addon_disable(module=ADDON_MODULE)
        if os.path.lexists(self.bl_mi_addon_dir):
            os.remove(self.bl_mi_addon_dir)

    def pytest_runtest_setup(self, item):
        bpy.ops.wm.read_homefile(use_empty=True)
        if ADDON_MODULE not in bpy.context.preferences.addons:
            raise RuntimeError("Plugin was disabled by test reset")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Runs mitsuba-blender pytest tests")
    parser.add_argument('--mitsuba',
                        default=None,
                        help='Specify a custom path to the Mitsuba installation.')

    argv = sys.argv[1:]
    pytest_args = ['tests']
    try:
        index = argv.index('--')
        script_args = argv[:index]
        pytest_args += argv[index + 1:]
    except ValueError:
        script_args = argv

    args, _ = parser.parse_known_args(script_args)
    if args.mitsuba:
        print(f'Using custom Mitsuba path: {args.mitsuba}')

    try:
        exit_code = pytest.main(pytest_args, plugins=[SetupPlugin(args.mitsuba)])
    except Exception as e:
        print(e)
        exit_code = 1

    sys.exit(exit_code)
