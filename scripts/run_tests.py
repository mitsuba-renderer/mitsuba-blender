import sys
import os

import bpy
import pytest

class SetupPlugin:
    def __init__(self):
        mi_addon_root_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        self.mi_addon_dir = os.path.join(mi_addon_root_dir, 'mitsuba2-blender')
        self.bl_addon_dir = os.path.join(bpy.utils.user_resource('SCRIPTS', 'addons'), 'mitsuba2-blender')
        sys.path.append(self.mi_addon_dir)

    def pytest_configure(self, config):
        if os.path.exists(self.bl_addon_dir):
            os.remove(self.bl_addon_dir)
        
        if sys.platform == 'win32':
            import _winapi
            _winapi.CreateJunction(str(self.mi_addon_dir), str(self.bl_addon_dir))
        else:
            os.symlink(self.mi_addon_dir, self.bl_addon_dir, target_is_directory=True)
        
        bpy.ops.preferences.addon_enable(module='mitsuba2-blender')
        bpy.context.preferences.addons['mitsuba2-blender'].preferences.mitsuba_path = "C:\\Users\\doria\\Documents\\EPFL\\sp-blender-addon\\mitsuba3\\build\\Release"

    def pytest_unconfigure(self):
        bpy.ops.preferences.addon_disable(module='mitsuba2-blender')
        
        os.remove(self.bl_addon_dir)

pytest_args = ["tests", "-v"]
try:
    exit_code = pytest.main(pytest_args, plugins=[SetupPlugin()])
except Exception as e:
    print(e)
    exit_code = 1

sys.exit(exit_code)
