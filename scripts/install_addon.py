# This script installs the mitsuba-blender addon inside of the running Blender instance.
# To use this script, run it using Blender's command line arguments.
# E.g., blender.exe -b --python install_addon.py

import sys
import os

import bpy

if __name__ == '__main__':
    mi_addon_root_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    mi_addon_dir = os.path.join(mi_addon_root_dir, 'mitsuba-blender')
    bl_script_dir = None
    for dir in bpy.utils.script_paths(use_user=True):
        if dir.endswith('scripts'):
            bl_script_dir = dir
    if bl_script_dir is None:
        raise RuntimeError('Cannot resolve Blender script directory')
    bl_addon_dir = os.path.join(bl_script_dir, 'addons')
    bl_mi_addon_dir = os.path.join(bl_addon_dir, 'mitsuba-blender')

    # Create a symlink from the addon to the Blender script folder
    if not os.path.exists(bl_mi_addon_dir):
        if sys.platform == 'win32':
            import _winapi
            _winapi.CreateJunction(str(mi_addon_dir), str(bl_mi_addon_dir))
        else:
            os.symlink(mi_addon_dir, bl_mi_addon_dir, target_is_directory=True)
    
    if 'mitsuba-blender' not in bpy.context.preferences.addons:
        if bpy.ops.preferences.addon_enable(module='mitsuba-blender') != {'FINISHED'}:
            raise RuntimeError('Cannot enable mitsuba2-blender addon')
        bpy.ops.wm.save_userpref()
