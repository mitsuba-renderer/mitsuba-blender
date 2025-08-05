# Import/re-import all files in this folder to register plugins
import importlib
import mitsuba as mi

if mi.variant() is not None and not mi.variant().startswith('scalar'):
    from . import spherelight
    importlib.reload(spherelight)