import bpy

from ..utils import *
from ..operators.pip_installer import MITSUBA_OT_install_pip_dependencies

def mitsuba_update_callback(prefs, context):
    '''
    Callback executed when the Mitsuba path in set in the add-on preferences
    '''
    from .. import register, unregister

    if prefs.use_custom_mitsuba and len(prefs.mitsuba_path) > 0 and not prefs.mitsuba_path in sys.path:
        # Update the Python path to include Mitsuba
        update_python_paths(prefs.mitsuba_path)

    # If the addon was not properly initialized and the path has changed, or if there is an existing mitsuba loaded, require a restart
    prefs.require_restart = 'mitsuba' in sys.modules 

    if not prefs.require_restart:
        # Since Mitsuba was never loaded, it is safe to simply re-register the add-on
        unregister()
        register(context)

    # Save user preferences
    if prefs.initialized:
        bpy.ops.wm.save_userpref()

class MitsubaPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__.split('.')[0]

    initialized : bpy.props.BoolProperty(
        name = 'Is Mitsuba addon initialized',
    )

    require_restart : bpy.props.BoolProperty(
        name = 'Require a blender restart',
    )

    valid_version : bpy.props.BoolProperty(
        name = 'Is the Mitsuba version high enough',
    )

    has_pip_mitsuba : bpy.props.BoolProperty(
        name = 'Is pip Mitsuba installed'
    )

    mitsuba_status_message : bpy.props.StringProperty(
        name = 'Mitsuba dependencies status message',
        default = 'Enter the path to your local Mitsuba folder (root folder)',
    )

    use_custom_mitsuba : bpy.props.BoolProperty(
        name = 'Use a custom Mitsuba build (not recommended)',
        default = False,
        update = mitsuba_update_callback
    )

    mitsuba_path : bpy.props.StringProperty(
        name = 'Path to Mitsuba',
        description = 'Path to the local Mitsuba build folder',
        default = find_mitsuba(),
        subtype = 'DIR_PATH',
        update = mitsuba_update_callback,
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "use_custom_mitsuba")

        row = layout.row()
        if self.require_restart:
            row.alert = True
            row.label(text="A restart is required to apply the changes", icon='ERROR')
        elif not self.initialized:
            # This should always show up first as self.require_restart is reset to True when registering
            row.alert = True
            row.label(text=self.mitsuba_status_message, icon='ERROR')
        else:
            row.alert = False
            row.label(text=self.mitsuba_status_message, icon='CHECKMARK')

        if self.use_custom_mitsuba:
            box = layout.box()
            box.prop(self, 'mitsuba_path')
        else:
            operator_text = 'Install mitsuba'
            if self.has_pip_mitsuba and not self.valid_version:
                operator_text = 'Update mitsuba'
            layout.operator(MITSUBA_OT_install_pip_dependencies.bl_idname, text=operator_text)

