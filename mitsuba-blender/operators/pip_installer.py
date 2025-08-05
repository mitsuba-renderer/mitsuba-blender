import bpy
import sys, subprocess
from ..utils import get_addon_preferences, check_mitsuba_version, get_pip_mi_version

class MITSUBA_OT_install_pip_dependencies(bpy.types.Operator):
    bl_idname = 'mitsuba.install_pip_dependencies'
    bl_label = 'Install Mitsuba pip dependencies'
    bl_description = 'Use pip to install the add-on\'s required dependencies'

    @classmethod
    def poll(cls, context):
        prefs = get_addon_preferences(context)
        active = not prefs.has_pip_mitsuba or not prefs.valid_version
        if prefs.has_pip_mitsuba and not prefs.valid_version:
            # If we just updated via pip, we can disable the button
            active = not check_mitsuba_version(get_pip_mi_version())

        return active

    def execute(self, context):
        from .. import unregister, register, MI_VERSION, MI_VERSION_STR
        result = subprocess.run([sys.executable, '-m', 'pip', 'install', f'mitsuba>={MI_VERSION_STR}', '--force-reinstall'], capture_output=False)
        if result.returncode != 0:
            self.report({'ERROR'}, f'Failed to install Mitsuba with return code {result.returncode}.')
            return {'CANCELLED'}
        

        prefs = get_addon_preferences(context)
        # Require a restart to update the path to mitsuba
        prefs.require_restart = 'mitsuba' in sys.modules
        if not prefs.require_restart:
            # Since Mitsuba was never loaded, it is safe to simply re-register the add-on
            unregister()
            register(context)

        return {'FINISHED'}
