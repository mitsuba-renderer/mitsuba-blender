

def register_plugins():
    '''
    Register the addon's Python texture plugins with Mitsuba
    '''
    import mitsuba as mi
    import drjit as dr

    from .textures import color_ramp, math, hue_saturation, rgb_curve, mix, invert, brightness_contrast

    color_ramp.register(mi, dr)
    math.register(mi, dr)
    hue_saturation.register(mi, dr)
    rgb_curve.register(mi, dr)
    mix.register(mi, dr)
    invert.register(mi, dr)
    brightness_contrast.register(mi, dr)
