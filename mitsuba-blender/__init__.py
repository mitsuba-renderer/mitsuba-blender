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

from . import (
    engine, nodes, properties, operators, ui
)

from .utils import pip_ensure, pip_package_install, pip_package_version

DEPS_MITSUBA_VERSION = '3.4.0'

def get_addon_preferences(context):
    return context.preferences.addons[__name__].preferences

def get_addon_version_string():
    return f'{".".join(str(e) for e in bl_info["version"])}{bl_info["warning"] if "warning" in bl_info else ""}'

def get_mitsuba_version_string():
    import mitsuba
    return mitsuba.__version__

def get_addon_info_string():
    return f'mitsuba-blender v{get_addon_version_string()} registered (with mitsuba v{get_mitsuba_version_string()})'

def init_mitsuba():
    # Make sure we can load Mitsuba from Blender
    try:
        os.environ['DRJIT_NO_RTLD_DEEPBIND'] = 'True'
        should_reload_mitsuba = 'mitsuba' in sys.modules
        import mitsuba
        # If Mitsuba was already loaded and we change the path, we need to reload it, since the import above will be ignored
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

def register_addon(context):
    prefs = get_addon_preferences(context)
    prefs.status_message = ''

    could_init_mitsuba = False
    if prefs.using_mitsuba_custom_path:
        prefs.update_additional_custom_paths(context)
        could_init_mitsuba = init_mitsuba()
        if could_init_mitsuba:
            prefs.mitsuba_custom_version = get_mitsuba_version_string()
            if prefs.has_valid_mitsuba_custom_version:
                prefs.status_message = f'Found custom Mitsuba v{prefs.mitsuba_custom_version}.'
            else:
                prefs.status_message = f'Found custom Mitsuba v{prefs.mitsuba_custom_version}. Supported version is v{DEPS_MITSUBA_VERSION}.'
        else:
            prefs.status_message = 'Failed to load custom Mitsuba. Please verify the path to the build directory.'
    elif prefs.is_mitsuba_installed:
        if prefs.has_valid_mitsuba_version:
            could_init_mitsuba = init_mitsuba()
            if could_init_mitsuba:
                prefs.status_message = f'Found pip Mitsuba v{get_mitsuba_version_string()}.'
            else:
                prefs.status_message = 'Failed to load Mitsuba package.'
        else:
            prefs.status_message = f'Found pip Mitsuba v{prefs.installed_mitsuba_version}. Supported version is v{DEPS_MITSUBA_VERSION}.'
    else:
        prefs.status_message = 'Mitsuba dependencies not installed.'

    prefs.is_mitsuba_initialized = could_init_mitsuba

    if could_init_mitsuba:
        properties.register()
        operators.register()
        ui.register()
        engine.register()
        nodes.register()

    return could_init_mitsuba

def unregister_addon():
    '''
    Try unregistering Addon classes.
    This may fail if Mitsuba wasn't found, hence the try catch guard
    '''
    try:
        nodes.unregister()
        engine.unregister()
        ui.unregister()
        operators.unregister()
        properties.unregister()
        return True
    except RuntimeError:
        return False

def reload_addon(context):
    unregister_addon()
    if register_addon(context):
        # Save user preferences
        bpy.ops.wm.save_userpref()

class MITSUBA_OT_download_package_dependencies(Operator):
    bl_idname = 'mitsuba.download_package_dependencies'
    bl_label = 'Download the recommended Mitsuba dependencies'
    bl_description = 'Use pip to download the add-on\'s required dependencies'

    @classmethod
    def poll(cls, context):
        prefs = get_addon_preferences(context)
        return not prefs.is_mitsuba_installed or not prefs.has_valid_mitsuba_version

    def execute(self, context):
        if not pip_package_install('mitsuba', version=DEPS_MITSUBA_VERSION):
            self.report({'ERROR'}, 'Failed to download Mitsuba package with pip.')
            return {'CANCELLED'}

        prefs = get_addon_preferences(context)
        prefs.is_mitsuba_installed = True
        prefs.installed_mitsuba_version = DEPS_MITSUBA_VERSION

        reload_addon(context)

        return {'FINISHED'}

class MitsubaPreferences(AddonPreferences):
    bl_idname = __name__

    is_mitsuba_initialized : BoolProperty(
        name = 'Is Mitsuba initialized',
    )

    is_mitsuba_installed : BoolProperty(
        name = 'Is the Mitsuba package installed',
    )

    is_restart_required : BoolProperty(
        name = 'Is a Blender restart required',
    )

    def update_installed_mitsuba_version(self, context):
        self.has_valid_mitsuba_version = self.installed_mitsuba_version == DEPS_MITSUBA_VERSION

    installed_mitsuba_version : StringProperty(
        name = 'Installed Mitsuba dependencies version string',
        default = '',
        update = update_installed_mitsuba_version,
    )

    has_valid_mitsuba_version : BoolProperty(
        name = 'Has the correct version of dependencies'
    )

    status_message : StringProperty(
        name = 'Add-on status message',
        default = '',
    )

    # Advanced settings

    def clean_additional_custom_paths(self, context):
        # Remove old values from system PATH and sys.path
        if self.additional_python_path in sys.path:
            sys.path.remove(self.additional_python_path)
        if self.additional_path and self.additional_path in os.environ['PATH']:
            items = os.environ['PATH'].split(os.pathsep)
            items.remove(self.additional_path)
            os.environ['PATH'] = os.pathsep.join(items)

    def update_additional_custom_paths(self, context):
        build_path = bpy.path.abspath(self.mitsuba_custom_path)
        if len(build_path) > 0:
            self.clean_additional_custom_paths(context)

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

    def update_mitsuba_custom_path(self, context):
        if self.is_mitsuba_initialized:
            self.is_restart_required = True
        if self.using_mitsuba_custom_path and len(self.mitsuba_custom_path) > 0:
            self.update_additional_custom_paths(context)
            if not self.is_mitsuba_initialized:
                reload_addon(context)

    def update_using_mitsuba_custom_path(self, context):
        self.require_restart = True
        if self.using_mitsuba_custom_path:
            self.update_mitsuba_custom_path(context)
        else:
            self.clean_additional_custom_paths(context)

    def update_mitsuba_custom_version(self, context):
        self.has_valid_mitsuba_custom_version = self.mitsuba_custom_version == DEPS_MITSUBA_VERSION

    using_mitsuba_custom_path : BoolProperty(
        name = 'Using custom Mitsuba path',
        update = update_using_mitsuba_custom_path,
    )

    mitsuba_custom_version : StringProperty(
        name = 'Custom Mitsuba build version',
        default = '',
        update = update_mitsuba_custom_version,
    )

    has_valid_mitsuba_custom_version : BoolProperty(
        name = 'Has the correct version of custom Mitsuba build'
    )

    mitsuba_custom_path : StringProperty(
        name = 'Custom Mitsuba path',
        description = 'Path to the custom Mitsuba build directory',
        default = '',
        subtype = 'DIR_PATH',
        update = update_mitsuba_custom_path,
    )

    mitsuba_custom_version : StringProperty(
        name = 'Custom Mitsuba build version',
        default = '',
        update = update_mitsuba_custom_version,
    )

    has_valid_mitsuba_custom_version : BoolProperty(
        name = 'Has the correct version of custom Mitsuba build'
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
        icon = 'ERROR'
        row.alert = True
        if self.is_restart_required:
            self.status_message = 'A restart is required to apply the changes.'
        elif self.is_mitsuba_initialized and (not self.using_mitsuba_custom_path or (self.using_mitsuba_custom_path and self.has_valid_mitsuba_custom_version)):
            icon = 'CHECKMARK'
            row.alert = False
        row.label(text=self.status_message, icon=icon)

        download_operator_text = 'Install Mitsuba'
        if self.is_mitsuba_installed and not self.has_valid_mitsuba_version:
            download_operator_text = 'Update Mitsuba'
        layout.operator(MITSUBA_OT_download_package_dependencies.bl_idname, text=download_operator_text)

        box = layout.box()
        box.label(text='Advanced Settings')
        box.prop(self, 'using_mitsuba_custom_path', text=f'Use custom Mitsuba path (Supported version is v{DEPS_MITSUBA_VERSION})')
        if self.using_mitsuba_custom_path:
            box.prop(self, 'mitsuba_custom_path')
        
classes = (
    MITSUBA_OT_download_package_dependencies,
    MitsubaPreferences,
)

def register():
    for cls in classes:
        register_class(cls)

    if not pip_ensure():
        raise RuntimeError('Cannot activate mitsuba-blender add-on. Python pip module cannot be initialized.')

    context = bpy.context
    prefs = get_addon_preferences(context)
    prefs.is_mitsuba_initialized = False
    mitsuba_installed_version = pip_package_version('mitsuba')
    prefs.is_mitsuba_installed = mitsuba_installed_version != None
    prefs.installed_mitsuba_version = mitsuba_installed_version if mitsuba_installed_version is not None else ''
    prefs.is_restart_required = False

    if register_addon(context):
        print(get_addon_info_string())

def unregister():
    for cls in classes:
        unregister_class(cls)
    if not unregister_addon():
        print('FAILED TO UNREGISTER ADDON')

if __name__ == '__main__':
    register()
