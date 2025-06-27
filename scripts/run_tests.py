import sys
import os

import bpy
import pytest

class SetupPlugin:
    def __init__(self):
        mi_addon_root_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        self.mi_addon_dir = os.path.join(mi_addon_root_dir, 'mitsuba-blender')
        self.bl_addon_dir  = bpy.utils.user_resource('SCRIPTS', path='addons', create=True)
        bpy.utils.refresh_script_paths()
        self.bl_mi_addon_dir = os.path.join(self.bl_addon_dir, 'mitsuba-blender')

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

        if not bpy.context.preferences.addons['mitsuba-blender'].preferences.initialized:
            raise RuntimeError('Failed to initialize Mitsuba library')

    def pytest_unconfigure(self):
        bpy.ops.preferences.addon_disable(module='mitsuba-blender')
        # Remove the symlink
        os.remove(self.bl_mi_addon_dir)

    def pytest_runtest_setup(self, item):
        bpy.ops.wm.read_homefile(use_empty=True)
        if 'mitsuba-blender' not in bpy.context.preferences.addons:
            raise RuntimeError("Plugin was disabled by test reset")

if __name__ == '__main__':
    pytest_args = ["tests"]

    try:
        pytest_args += sys.argv[sys.argv.index('--')+1:]
    except ValueError:
        pass

    try:
        exit_code = pytest.main(pytest_args, plugins=[SetupPlugin()])
    except Exception as e:
        print(e)
        exit_code = 1

    sys.exit(exit_code)
