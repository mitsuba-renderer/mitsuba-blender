# Import/re-import all files in this folder to register plugins
import importlib
import mitsuba as mi

if mi.variant() is not None and not mi.variant().startswith('scalar'):
    from . import common
    importlib.reload(common)

    from . import clamp
    importlib.reload(clamp)

    from . import combine_color
    importlib.reload(combine_color)

    from . import hue_saturation
    importlib.reload(hue_saturation)

    from . import map_range
    importlib.reload(map_range)

    from . import noise
    importlib.reload(noise)

    from . import rgb_to_bw
    importlib.reload(rgb_to_bw)

    from . import separate_rgb
    importlib.reload(separate_rgb)

    from . import udim
    importlib.reload(udim)
