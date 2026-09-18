import glob
import os

PLUGINS_DIR = os.path.dirname(os.path.abspath(__file__))


def module_files():
    '''
    Files of the modules in the subfolders of this package, each defining a
    ``register(mi, dr)`` function. The exporter copies a subset of this
    package next to a scene (see io/exporter/plugin_bundle.py).
    '''
    return [path for path in sorted(glob.glob(os.path.join(PLUGINS_DIR, '*', '*.py')))
            if os.path.basename(path) != '__init__.py']


def _register_all():
    import importlib
    import mitsuba as mi
    import drjit as dr

    for path in module_files():
        name = os.path.relpath(path, PLUGINS_DIR)[:-3].replace(os.sep, '.')
        importlib.import_module('.' + name, __name__).register(mi, dr)


def register_plugins():
    '''Called by the Blender addon after set_variant.'''
    _register_all()


# Entry-point auto-discovery: Mitsuba imports this module after
# set_variant and reloads it on every variant change.
import mitsuba as mi
if mi.variant() is not None:
    _register_all()
