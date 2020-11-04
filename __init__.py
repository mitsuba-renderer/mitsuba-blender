bl_info = {
    "name": "Mitsuba2-Blender",
    "author": "Baptiste Nicolet",
    "version": (0, 1),
    "blender": (2, 80, 0),
    "category": "Exporter",
    "location": "File > Export > Mitsuba 2",
    "description": "Mitsuba2 export for Blender",
    "warning": "alpha0",
    "support": "TESTING"
}

import bpy
import os
import sys
from bpy.props import StringProperty
from bpy.types import AddonPreferences
from . import export, engine
#from export import MitsubaFileExport, MitsubaPrefs

def get_mitsuba_path():
    # Try to get the path to the Mitsuba 2 root folder
    tokens = os.getenv('MITSUBA_DIR')
    if tokens:
        for token in tokens.split(':'):
            path = os.path.join(token, 'build')
            if os.path.isdir(path):
                return path
    return ""

def set_path(context):
    '''
    Set the different variables necessary to run the addon properly.
    Add the path to mitsuba binaries to the PATH env var.
    Append the path to the python libs to sys.path
    '''
    prefs = context.preferences.addons[__name__].preferences
    mts_build = bpy.path.abspath(prefs.mitsuba_path)
    # Add path to the binaries to the system PATH
    prefs.os_path = mts_build
    if prefs.os_path not in os.environ['PATH']:
        os.environ['PATH'] += os.pathsep + prefs.os_path
    # Add path to python libs to sys.path
    prefs.python_path = os.path.join(mts_build, 'python')
    if prefs.python_path not in sys.path:
        sys.path.append(prefs.python_path)
    # Make sure we can load mitsuba from blender
    try:
        reload_mitsuba = 'mitsuba' in sys.modules
        import mitsuba
        # If mitsuba was already loaded and we change the path, we need to reload it, since the import above will be ignored
        if reload_mitsuba:
            import importlib
            importlib.reload(mitsuba)
        mitsuba.set_variant('scalar_rgb')
        return True
    except ModuleNotFoundError:
        return False

def try_registering(context):
    '''
    Only register Addon Classes if mitsuba can be found.

    Params
    ------

    context: Blender context
    '''
    prefs = context.preferences.addons[__name__].preferences
    prefs.ok_msg = ''
    prefs.error_msg = ''
    if set_path(context):
        export.register()
        engine.register()
        # Mitsuba was found, set the global threading environment
        from mitsuba.core import ThreadEnvironment
        bpy.types.Scene.thread_env = ThreadEnvironment()
        prefs.ok_msg = "Found Mitsuba"
        return True
    else:
        prefs.error_msg = "Failed to import Mitsuba 2. Please verify the path to the build directory."
        return False

def try_unregistering():
    '''
    Try unregistering Addon classes.
    This may fail if Mitsuba wasn't found, hence the try catch guard
    '''
    try:
        export.unregister()
        engine.unregister()
        return True
    except RuntimeError:
        return False

def reload_mts(self, context):
    try_unregistering()
    prefs = context.preferences.addons[__name__].preferences
    # Remove what we added in set_path
    if prefs.python_path in sys.path:
        sys.path.remove(prefs.python_path)
    if prefs.os_path in os.environ['PATH']:
        items = os.environ['PATH'].split(os.pathsep)
        items.remove(prefs.os_path)
        os.environ['PATH'] = os.pathsep.join(items)

    if try_registering(context):
        bpy.ops.wm.save_userpref() #Save the working path

class MitsubaPrefs(AddonPreferences):

    bl_idname = __name__

    mitsuba_path : StringProperty(
        name="Build Path",
        description="Path to the Mitsuba 2 build directory",
        subtype='DIR_PATH',
        default=get_mitsuba_path(),
        update=reload_mts
        )

    ok_msg : StringProperty(
        name = "Message",
        default = "",
        options = {'HIDDEN'}
        )

    error_msg : StringProperty(
        name = "Error Message",
        default = "",
        options = {'HIDDEN'}
        )

    os_path : StringProperty(
        name = "Addition to PATH",
        default="",
        subtype='DIR_PATH',
        options = {'HIDDEN'}
    )

    python_path : StringProperty(
        name = "Addition to sys.path",
        default="",
        subtype='DIR_PATH',
        options = {'HIDDEN'}
    )

    def draw(self, context):
        layout = self.layout
        if self.error_msg:
            sub = layout.row()
            sub.alert = True
            sub.label(text=self.error_msg, icon='ERROR')
        if self.ok_msg:
            sub = layout.row()
            sub.label(text=self.ok_msg, icon='CHECKMARK')
        layout.prop(self, "mitsuba_path")

def register():
    bpy.utils.register_class(MitsubaPrefs)
    try_registering(bpy.context)

def unregister():
    bpy.utils.unregister_class(MitsubaPrefs)
    try_unregistering()

if __name__ == '__main__':
    register()
