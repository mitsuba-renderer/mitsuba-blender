
def _register_all():
    import mitsuba as mi
    import drjit as dr

    from .textures import (color_ramp, math, hue_saturation, rgb_curve, mix,
                           invert, brightness_contrast, rgb_to_bw, map_range,
                           combine_xyz, separate_xyz, separate_color,
                           combine_color, vect_math, common, normal_map,
                           tex_noise)

    color_ramp.register(mi, dr)
    hue_saturation.register(mi, dr)
    rgb_curve.register(mi, dr)
    mix.register(mi, dr)
    invert.register(mi, dr)
    brightness_contrast.register(mi, dr)
    map_range.register(mi, dr)
    combine_xyz.register(mi, dr)
    separate_xyz.register(mi, dr)
    separate_color.register(mi, dr)
    combine_color.register(mi, dr)
    vect_math.register(mi, dr)
    common.register(mi, dr)
    normal_map.register(mi, dr)
    tex_noise.register(mi, dr)


def register_plugins():
    '''Called by the Blender addon after set_variant.'''
    _register_all()


# Entry-point auto-discovery: Mitsuba imports this module after
# set_variant and reloads it on every variant change.
import mitsuba as mi
if mi.variant() is not None:
    _register_all()
