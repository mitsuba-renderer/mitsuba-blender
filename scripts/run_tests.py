import sys
import os

import bpy
import pytest

class SetupPlugin:
    def __init__(self, args):
        # If this flag is set, skip the add-on installation process.
        # This assumes that the add-on is already installed in the executing Blender instance.
        self.skip_install = args['--skip-install']

        # If this flag is set, Blender's temporary directory is set to a local folder.
        # This is useful to save crash logs in a common place across environments.
        # This is intended to be used on CI environments only!
        self.local_tmp = args['--local-tmp']

        # Find Blender's add-on installation folder
        bl_script_dirs = bpy.utils.script_paths(use_user=True)
        self.bl_script_dir = None
        for dir in bl_script_dirs:
            if dir.endswith('scripts'):
                self.bl_script_dir = dir
        if self.bl_script_dir is None:
            raise RuntimeError('Cannot resolve Blender script directory')
        
        # Define relevant paths
        self.mi_addon_root_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        self.mi_addon_dir = os.path.join(self.mi_addon_root_dir, 'mitsuba-blender')
        self.bl_addon_dir = os.path.join(self.bl_script_dir, 'addons')
        self.bl_mi_addon_dir = os.path.join(self.bl_addon_dir, 'mitsuba-blender')
        self.bl_tmp_dir = os.path.join(self.mi_addon_root_dir, 'tmp')

        # Add the add-on directory to the system path. This is needed for computing coverage.
        sys.path.append(self.mi_addon_dir)

    def pytest_configure(self, config):
        if self.local_tmp:
            os.makedirs(self.bl_tmp_dir, exist_ok=True)
            bpy.context.preferences.filepaths.temporary_directory = str(self.bl_tmp_dir)

        if not self.skip_install:
            if os.path.exists(self.bl_mi_addon_dir):
                os.remove(self.bl_mi_addon_dir)
            
            # Create a symlink from the addon to the Blender script folder
            if sys.platform == 'win32':
                import _winapi
                _winapi.CreateJunction(str(self.mi_addon_dir), str(self.bl_mi_addon_dir))
            else:
                os.symlink(self.mi_addon_dir, self.bl_mi_addon_dir, target_is_directory=True)
        
        if bpy.ops.preferences.addon_enable(module='mitsuba-blender') != {'FINISHED'}:
            raise RuntimeError('Cannot enable mitsuba2-blender addon')

        if not bpy.context.preferences.addons['mitsuba-blender'].preferences.is_mitsuba_initialized:
            raise RuntimeError('Failed to initialize Mitsuba library')

        print(bpy.context.preferences.filepaths.temporary_directory)            

    def pytest_unconfigure(self):
        if not self.skip_install:
            bpy.ops.preferences.addon_disable(module='mitsuba-blender')
            bpy.ops.wm.save_userpref()
            # Remove the symlink
            os.remove(self.bl_mi_addon_dir)

    def pytest_runtest_setup(self, item):
        bpy.ops.wm.read_homefile(use_empty=True)
        if 'mitsuba-blender' not in bpy.context.preferences.addons:
            raise RuntimeError("Plugin was disabled by test reset")

def main(args):
    pytest_args = ["tests"]

    try:
        pytest_args += args[args.index('--')+1:]
    except ValueError:
        pass

    other_args = {
        '--skip-install': False,
        '--local-tmp': False,
    }

    # Parse additional custom flags
    temp_args = other_args.copy()
    for arg in other_args.keys():
        if arg in pytest_args:
            pytest_args.remove(arg)
            temp_args[arg] = True
    other_args = temp_args

    try:
        return pytest.main(pytest_args, plugins=[SetupPlugin(other_args)])
    except Exception as e:
        print(e)
    return 1

if __name__ == '__main__':
    sys.exit(main(sys.argv))
