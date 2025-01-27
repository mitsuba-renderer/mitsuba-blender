bl_info = {
    'name': 'Mitsuba-Blender',
    'author': 'Baptiste Nicolet, Dorian Ros, Rami Tabbara, Sébastien Speierer',
    'version': (1, 0),
    'blender': (4, 0, 0),
    'category': 'Render',
    'location': 'File menu, render engine menu',
    'description': 'Mitsuba integration for Blender',
}

# Required Mitsuba version
MI_VERSION = [3, 6, 0]

import os, importlib
import bpy

from . import engine
from . import exporter
from . import importer
from . import operators
from . import panels
from . import properties
from . import utils
from . import logging

initialized = False

# Register the add-on preferences panel first, to have access to it
bpy.utils.register_class(panels.addon.MitsubaPreferences)

def register(context=bpy.context):
    global initialized
    initialized = False

    # Lookup add-on preferences
    prefs = context.preferences.addons['mitsuba_blender'].preferences

    # Make sure a path is specified for Mitsuba
    if prefs.mitsuba_path == '':
        prefs.mitsuba_status_message = 'Failed to initialize Mitsuba: invalid Mitsuba path!'
        prefs.initialized = False
        return False

    # Update the Python path to include Mitsuba and Mitsuba
    utils.update_python_paths(prefs.mitsuba_path)

    # Test Mitsuba module
    try:
        os.environ['DRJIT_NO_RTLD_DEEPBIND'] = 'True'
        import mitsuba as mi
        mi.set_variant(*[v for v in mi.variants() if not v.startswith('scalar')])

        # Check Mitsuba version
        v = [int(v) for v in mi.__version__.split('.')]
        valid_version = False
        if v[0] > MI_VERSION[0]:
            valid_version = True
        elif v[0] == MI_VERSION[0]:
            if v[1] > MI_VERSION[1]:
                valid_version = True
            elif v[1] == MI_VERSION[1]:
                if v[2] >= MI_VERSION[2]:
                    valid_version = True
        if not valid_version:
            prefs.mitsuba_status_message = f'Need to upgrade your Mitsuba installation! (found {mitsuba_version}, need >= {MI_VERSION})'
            prefs.initialized = False
        else:
            # Set the global threading environment
            bpy.types.Scene.thread_env = mi.ThreadEnvironment()
            prefs.initialized = True
    except ModuleNotFoundError as e:
        prefs.mitsuba_status_message = str(e)
        prefs.initialized = False

    if not prefs.initialized:
        prefs.mitsuba_status_message = f'Failed to register the mitsuba_blender addon: {prefs.mitsuba_status_message}'
        print(prefs.mitsuba_status_message)
        return

    initialized = True

    # Register plugins to Mitsuba
    from . import plugins

    logging.register()

    prefs.mitsuba_status_message = 'Successfully initialized Mitsuba'
    logging.info(f'mitsuba_blender registered (with mitsuba v{mi.MI_VERSION}, path={mi.__path__[0]})')

    engine.register()
    exporter.register()
    operators.register()
    panels.register()
    properties.register()

    # Reload Mitsuba to make sure we are up-to-date with the code
    import mitsuba
    importlib.reload(mitsuba)

def unregister():
    global initialized
    if initialized:
        bpy.types.Scene.thread_env = None
        engine.unregister()
        exporter.unregister()
        operators.unregister()
        panels.unregister()
        properties.unregister()
        logging.unregister()
