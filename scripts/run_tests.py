import argparse
import sys
import os

import bpy
import pytest

class SetupPlugin:
    def __init__(self, custom_mitsuba_path: str | None = None):
        mi_addon_root_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        self.mi_addon_dir = os.path.join(mi_addon_root_dir, 'mitsuba-blender')
        self.bl_addon_dir  = bpy.utils.user_resource('SCRIPTS', path='addons', create=True)
        bpy.utils.refresh_script_paths()
        self.bl_mi_addon_dir = os.path.join(self.bl_addon_dir, 'mitsuba-blender')
        self.custom_mitsuba_path = custom_mitsuba_path

    def pytest_configure(self, config):
        if os.path.exists(self.bl_mi_addon_dir):
            os.remove(self.bl_mi_addon_dir)

        # Create a symlink from the addon to the Blender script folder
        if sys.platform == 'win32':
            import _winapi
            _winapi.CreateJunction(str(self.mi_addon_dir), str(self.bl_mi_addon_dir))
        else:
            os.symlink(self.mi_addon_dir, self.bl_mi_addon_dir, target_is_directory=True)

        if bpy.ops.preferences.addon_enable(module='mitsuba-blender') != {'FINISHED'}:
            raise RuntimeError('Cannot enable mitsuba-blender addon')

        if self.custom_mitsuba_path:
            bpy.context.preferences.addons['mitsuba-blender'].preferences.using_mitsuba_custom_path = True
            bpy.context.preferences.addons['mitsuba-blender'].preferences.mitsuba_custom_path = self.custom_mitsuba_path

        if not bpy.context.preferences.addons['mitsuba-blender'].preferences.is_mitsuba_initialized:
            status = bpy.context.preferences.addons['mitsuba-blender'].preferences.mitsuba_dependencies_status_message
            raise RuntimeError(f'Failed to initialize Mitsuba library: {status}')

    def pytest_unconfigure(self):
        bpy.ops.preferences.addon_disable(module='mitsuba-blender')
        # Remove the symlink
        os.remove(self.bl_mi_addon_dir)

    def pytest_runtest_setup(self, item):
        bpy.ops.wm.read_homefile(use_empty=True)
        if 'mitsuba-blender' not in bpy.context.preferences.addons:
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
