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
MI_VERSION_STR = '.'.join([str(i) for i in MI_VERSION])

import sys, os, importlib
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
bpy.utils.register_class(operators.pip_installer.MITSUBA_OT_install_pip_dependencies)
bpy.utils.register_class(panels.addon.MitsubaPreferences)

def register(context=bpy.context):
    global initialized
    initialized = False

    # Lookup add-on preferences
    prefs = utils.get_addon_preferences(context)
    prefs.require_restart = False

    if prefs.use_custom_mitsuba:
        # Update the Python path to include Mitsuba
        utils.update_python_paths(prefs.mitsuba_path)

        # Determine if the specified path points to a valid mitsuba build folder
        spec = importlib.util.find_spec('mitsuba')
        if spec is None:
            prefs.mitsuba_status_message = 'Failed to initialize Mitsuba: invalid Mitsuba path!'
            prefs.initialized = False
            return False
        elif not spec.origin.startswith(os.path.realpath(prefs.mitsuba_path)):
            prefs.mitsuba_status_message = 'Found a different build of Mitsuba than the one specified. Check that the path you specified is correct'
            prefs.initialized = False
            return False
    else:
        if not utils.ensure_pip():
            if sys.executable.startswith('/snap/'):
                prefs.mitsuba_status_message = 'You seem to be using a snap-installed blender, which is not recommended as it may prevent pip from installing mitsuba.'
            else:
                prefs.mitsuba_status_message = 'Failed to initialize pip. Make sure blender is installed and run with the right permissions.'
            prefs.initialized = False
            return False
        # Make sure Mitsuba was installed via pip
        prefs.has_pip_mitsuba = utils.get_pip_mi_version() is not None

    # Test Mitsuba module
    try:
        os.environ['DRJIT_NO_RTLD_DEEPBIND'] = 'True'
        import mitsuba as mi
        mi.set_variant(*[v for v in mi.variants() if not v.startswith('scalar')])
        # Check Mitsuba version
        prefs.valid_version = utils.check_mitsuba_version(mi.__version__)
        if not prefs.valid_version:
            prefs.mitsuba_status_message = f"You need to upgrade your Mitsuba installation (found {mi.__version__}, need >= {MI_VERSION_STR})."
            prefs.initialized = False
        else:
            # Set the global threading environment
            bpy.types.Scene.thread_env = mi.ThreadEnvironment()
            prefs.initialized = True
    except ModuleNotFoundError as e:
        prefs.mitsuba_status_message = str(e)
        if sys.executable.startswith('/snap/'):
            prefs.mitsuba_status_message = "Could not find Mitsuba. For snap versions of blender, make sure you run it with the --python-use-system-env flag."
        prefs.initialized = False
    except ImportError as e:
        if prefs.use_custom_mitsuba:
            prefs.mitsuba_status_message = f"Found Mitsuba but could not import it. Make sure that you compiled Mitsuba with a compatible Python version ({sys.version_info.major}.{sys.version_info.minor})."
        print(e)
        prefs.initialized = False

    if not prefs.initialized:
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
