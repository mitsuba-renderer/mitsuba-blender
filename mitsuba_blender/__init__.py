import os

# Dr.Jit requires this to be set before mitsuba is first imported.
os.environ.setdefault('DRJIT_NO_RTLD_DEEPBIND', '1')


def register():
    from bpy.utils import register_class
    from . import preferences
    register_class(preferences.MitsubaPreferences)
    if preferences.init_mitsuba():
        from . import properties, engine, ui, io
        from .plugins import register_plugins
        register_plugins()
        properties.register()
        engine.register()
        ui.register()
        io.register()
        print(f'mitsuba_blender registered '
              f'(with mitsuba v{preferences.mitsuba_version})')
    else:
        print(f'mitsuba_blender: could not load mitsuba: '
              f'{preferences.init_error}')


def unregister():
    from bpy.utils import unregister_class
    from . import preferences
    if preferences.mitsuba_version is not None:
        from . import properties, engine, ui, io
        io.unregister()
        ui.unregister()
        engine.unregister()
        properties.unregister()
        preferences.mitsuba_version = None
    unregister_class(preferences.MitsubaPreferences)
