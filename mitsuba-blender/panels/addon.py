import bpy

from ..utils import *

def mitsuba_path_update_callback(prefs, context):
    '''
    Callback executed when the Mitsuba path in set in the add-on preferences
    '''
    from .. import register, unregister

    if len(prefs.mitsuba_path) > 0 and not prefs.mitsuba_path in sys.path:
        # Update the Python path to include Mitsuba
        update_python_paths(prefs.mitsuba_path)

        # Reload mitsuba if necessary
        try:
            if 'mitsuba' in sys.modules:
                import mitsuba
                import importlib
                importlib.reload(mitsuba)
            else:
                import mitsuba
        except Exception as e:
            print('Failed to initialize Mitsuba:', e)
            prefs.initialized = False
            prefs.mitsuba_status_message = 'Failed to initialize Mitsuba: Invalid Mitsuba path!'
            return

        # Unregister and re-register the add-on to adopt the new changes
        unregister()
        register(context)

        # Save Mitsuba path to user preferences
        if prefs.initialized:
            bpy.ops.wm.save_userpref()

class MitsubaPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__.split('.')[0]

    initialized : bpy.props.BoolProperty(
        name = 'Is Mitsuba addon initialized',
    )

    mitsuba_status_message : bpy.props.StringProperty(
        name = 'Mitsuba dependencies status message',
        default = 'Enter the path to your local Mitsuba folder (root folder)',
    )

    mitsuba_path : bpy.props.StringProperty(
        name = 'Path to Mitsuba',
        description = 'Path to the local Mitsuba codebase (root folder)',
        default = find_mitsuba(),
        subtype = 'DIR_PATH',
        update = mitsuba_path_update_callback,
    )

    def draw(self, context):
        layout = self.layout

        row = layout.row()
        if self.initialized:
            row.alert = False
            row.label(text=self.mitsuba_status_message, icon='CHECKMARK')
        else:
            row.alert = True
            row.label(text=self.mitsuba_status_message, icon='ERROR')

        box = layout.box()
        box.prop(self, 'mitsuba_path')
