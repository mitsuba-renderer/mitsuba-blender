import os
import sys

# Dr.Jit requires this to be set before mitsuba is first imported.
os.environ.setdefault('DRJIT_NO_RTLD_DEEPBIND', '1')

import bpy
from bpy.props import StringProperty
from bpy.types import AddonPreferences
from bpy.utils import register_class, unregister_class

# Version string of the loaded mitsuba module, or None with the reason in
# init_error. Filled in by register().
mitsuba_version = None
init_error = ''
_registered_path = None


class MitsubaPreferences(AddonPreferences):
    bl_idname = __package__

    custom_mitsuba_path: StringProperty(
        name = 'Custom Mitsuba path',
        description = 'Optional directory containing a custom mitsuba Python '
                      'package (e.g. <build>/python), used instead of the '
                      'bundled one. Takes effect after restarting Blender',
        default = '',
        subtype = 'DIR_PATH',
    )

    def draw(self, context):
        layout = self.layout
        if mitsuba_version is not None:
            layout.label(text=f'Using Mitsuba v{mitsuba_version}.', icon='CHECKMARK')
        else:
            row = layout.row()
            row.alert = True
            row.label(text=f'Failed to load Mitsuba: {init_error}', icon='ERROR')
        layout.prop(self, 'custom_mitsuba_path')
        if self.custom_mitsuba_path != _registered_path:
            layout.label(text='Restart Blender to apply the new path.', icon='INFO')


def _init_mitsuba():
    global mitsuba_version, init_error, _registered_path
    addon = bpy.context.preferences.addons.get(__package__)
    _registered_path = addon.preferences.custom_mitsuba_path if addon else ''
    try:
        if _registered_path:
            path = bpy.path.abspath(_registered_path)
            if path not in sys.path:
                sys.path.insert(0, path)
        import mitsuba
        mitsuba.set_variant('scalar_rgb')
        from .plugins import register_plugins
        register_plugins()

        mitsuba_version = mitsuba.__version__
        return True
    except Exception as e:
        mitsuba_version = None
        init_error = str(e)
        return False


def register():
    register_class(MitsubaPreferences)
    if _init_mitsuba():
        from . import properties, engine, ui, io
        properties.register()
        engine.register()
        ui.register()
        io.register()
        print(f'mitsuba_blender registered (with mitsuba v{mitsuba_version})')
    else:
        print(f'mitsuba_blender: could not load mitsuba: {init_error}')


def unregister():
    global mitsuba_version
    if mitsuba_version is not None:
        from . import properties, engine, ui, io
        io.unregister()
        ui.unregister()
        engine.unregister()
        properties.unregister()
        mitsuba_version = None
    unregister_class(MitsubaPreferences)
