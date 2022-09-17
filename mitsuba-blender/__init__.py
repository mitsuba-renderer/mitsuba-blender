bl_info = {
    'name': 'Mitsuba-Blender',
    'author': 'Baptiste Nicolet, Dorian Ros',
    'version': (0, 1),
    'blender': (2, 93, 0),
    'category': 'Render',
    'location': 'File menu, render engine menu',
    'description': 'Mitsuba integration for Blender',
    'wiki_url': 'https://github.com/mitsuba-renderer/mitsuba-blender/wiki',
    'tracker_url': 'https://github.com/mitsuba-renderer/mitsuba-blender/issues/new/choose',
    'warning': 'alpha',
}

import bpy
from bpy.props import StringProperty, BoolProperty
from bpy.types import Operator, AddonPreferences
from bpy.utils import register_class, unregister_class

import os
import sys
import subprocess

from . import io, engine

def get_addon_preferences(context):
    return context.preferences.addons[__name__].preferences

def init_mitsuba(context):
    # Make sure we can load mitsuba from blender
    try:
        should_reload_mitsuba = 'mitsuba' in sys.modules
        import mitsuba
        # If mitsuba was already loaded and we change the path, we need to reload it, since the import above will be ignored
        if should_reload_mitsuba:
            import importlib
            importlib.reload(mitsuba)
        mitsuba.set_variant('scalar_rgb')
        # Set the global threading environment
        from mitsuba import ThreadEnvironment
        bpy.types.Scene.thread_env = ThreadEnvironment()
        return True
    except ModuleNotFoundError:
        return False

def try_register_mitsuba(context):
    prefs = get_addon_preferences(context)
    prefs.mitsuba_dependencies_status_message = ''

    could_init_mitsuba = False
    if prefs.using_mitsuba_custom_path:
        update_additional_custom_paths(prefs, context)
        could_init_mitsuba = init_mitsuba(context)
        prefs.has_valid_mitsuba_custom_path = could_init_mitsuba
        if could_init_mitsuba:
            import mitsuba
            prefs.mitsuba_dependencies_status_message = f'Found custom Mitsuba v{mitsuba.__version__}.'
        else:
            prefs.mitsuba_dependencies_status_message = 'Failed to load custom Mitsuba. Please verify the path to the build directory.'
    elif prefs.has_pip_package:
        could_init_mitsuba = init_mitsuba(context)
        if could_init_mitsuba:
            import mitsuba
            prefs.mitsuba_dependencies_status_message = f'Found pip Mitsuba v{mitsuba.__version__}.'
        else:
            prefs.mitsuba_dependencies_status_message = 'Failed to load Mitsuba package.'
    else:
        prefs.mitsuba_dependencies_status_message = 'Mitsuba dependencies not installed.'

    prefs.is_mitsuba_initialized = could_init_mitsuba

    if could_init_mitsuba:
        io.register()
        engine.register()

    return could_init_mitsuba

def try_unregister_mitsuba():
    '''
    Try unregistering Addon classes.
    This may fail if Mitsuba wasn't found, hence the try catch guard
    '''
    try:
        io.unregister()
        engine.unregister()
        return True
    except RuntimeError:
        return False

def try_reload_mitsuba(context):
    try_unregister_mitsuba()
    if try_register_mitsuba(context):
        # Save user preferences
        bpy.ops.wm.save_userpref()

def ensure_pip():
    result = subprocess.run([sys.executable, '-m', 'ensurepip'], capture_output=True)
    return result.returncode == 0

def check_pip_dependencies(context):
    prefs = get_addon_preferences(context)
    result = subprocess.run([sys.executable, '-m', 'pip', 'show', 'mitsuba'], capture_output=True)
    prefs.has_pip_package = result.returncode == 0

def clean_additional_custom_paths(self, context):
    # Remove old values from system PATH and sys.path
    if self.additional_python_path in sys.path:
        sys.path.remove(self.additional_python_path)
    if self.additional_path and self.additional_path in os.environ['PATH']:
        items = os.environ['PATH'].split(os.pathsep)
        items.remove(self.additional_path)
        os.environ['PATH'] = os.pathsep.join(items)

def update_additional_custom_paths(self, context):
    print("update_additional_custom_paths")
    build_path = bpy.path.abspath(self.mitsuba_custom_path)
    if len(build_path) > 0:
        clean_additional_custom_paths(self, context)

        # Add path to the binaries to the system PATH
        self.additional_path = build_path
        if self.additional_path not in os.environ['PATH']:
            os.environ['PATH'] += os.pathsep + self.additional_path
        
        # Add path to python libs to sys.path
        self.additional_python_path = os.path.join(build_path, 'python')
        if self.additional_python_path not in sys.path:
            # NOTE: We insert in the first position here, so that the custom path
            #       supersede the pip version
            sys.path.insert(0, self.additional_python_path)

class MITSUBA_OT_install_pip_dependencies(Operator):
    bl_idname = 'mitsuba.install_pip_dependencies'
    bl_label = 'Install Mitsuba pip dependencies'
    bl_description = 'Use pip to install the add-on\'s required dependencies'

    @classmethod
    def poll(cls, context):
        prefs = get_addon_preferences(context)
        return not prefs.has_pip_package

    def execute(self, context):
        result = subprocess.run([sys.executable, '-m', 'pip', 'install', 'mitsuba'], capture_output=True)
        if result.returncode != 0:
            self.report({'ERROR'}, f'Failed to install Mitsuba with return code {result.returncode}.')
            return {'CANCELLED'} 

        prefs = get_addon_preferences(context)
        prefs.has_pip_package = True

        try_reload_mitsuba(context)

        return {'FINISHED'}

def update_using_mitsuba_custom_path(self, context):
    print("update_using_mitsuba_custom_path")
    if self.is_mitsuba_initialized:
        self.require_restart = True
    if self.using_mitsuba_custom_path:
        update_mitsuba_custom_path(self, context)
    else:
        clean_additional_custom_paths(self, context)

def update_mitsuba_custom_path(self, context):
    print("update_mitsuba_custom_path")
    if self.is_mitsuba_initialized:
        self.require_restart = True
    if self.using_mitsuba_custom_path and len(self.mitsuba_custom_path) > 0:
        update_additional_custom_paths(self, context)
        if not self.is_mitsuba_initialized:
            try_reload_mitsuba(context)

class MitsubaPreferences(AddonPreferences):
    bl_idname = __name__

    is_mitsuba_initialized : BoolProperty(
        name = 'Is Mitsuba initialized',
    )

    has_pip_package : BoolProperty(
        name = 'Has pip dependencies installed',
    )

    mitsuba_dependencies_status_message : StringProperty(
        name = 'Mitsuba dependencies status message',
        default = '',
    )

    require_restart : BoolProperty(
        name = 'Require a Blender restart',
    )

    # Advanced settings

    using_mitsuba_custom_path : BoolProperty(
        name = 'Using custom Mitsuba path',
        update = update_using_mitsuba_custom_path,
    )

    has_valid_mitsuba_custom_path : BoolProperty(
        name = 'Has valid custom Mitsuba path',
    )

    mitsuba_custom_path : StringProperty(
        name = 'Custom Mitsuba path',
        description = 'Path to the custom Mitsuba build directory',
        default = '',
        subtype = 'DIR_PATH',
        update = update_mitsuba_custom_path,
    )

    additional_path : StringProperty(
        name = 'Addition to PATH',
        default = '',
        subtype = 'DIR_PATH',
    )

    additional_python_path : StringProperty(
        name = 'Addition to sys.path',
        default = '',
        subtype = 'DIR_PATH',
    )

    def draw(self, context):
        layout = self.layout

        row = layout.row()
        if self.require_restart:
            self.mitsuba_dependencies_status_message = 'A restart is required to apply the changes.'
            row.alert = True
            icon = 'ERROR'
        elif self.has_pip_package or self.has_valid_mitsuba_custom_path:
            icon = 'CHECKMARK'
        else:
            icon = 'CANCEL'
            row.alert = True
        row.label(text=self.mitsuba_dependencies_status_message, icon=icon)

        layout.operator(MITSUBA_OT_install_pip_dependencies.bl_idname, text='Install dependencies using pip')

        box = layout.box()
        box.label(text='Advanced Settings')
        box.prop(self, 'using_mitsuba_custom_path', text='Use custom Mitsuba path')
        if self.using_mitsuba_custom_path:
            box.prop(self, 'mitsuba_custom_path')
        
classes = (
    MITSUBA_OT_install_pip_dependencies,
    MitsubaPreferences,
)

def register():
    for cls in classes:
        register_class(cls)

    context = bpy.context
    prefs = get_addon_preferences(context)
    prefs.require_restart = False

    if not ensure_pip():
        raise RuntimeError('Cannot activate mitsuba-blender add-on. Python pip module cannot be initialized.')

    check_pip_dependencies(context)
    if try_register_mitsuba(context):
        import mitsuba
        print(f'mitsuba-blender v{".".join(str(e) for e in bl_info["version"])}{bl_info["warning"] if "warning" in bl_info else ""} registered (with mitsuba v{mitsuba.__version__})')

def unregister():
    for cls in classes:
        unregister_class(cls)
    try_unregister_mitsuba()
