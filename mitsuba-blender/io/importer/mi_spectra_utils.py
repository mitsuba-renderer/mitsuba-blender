
def _get_mi_obj_properties(mi_obj):
    from mitsuba import traverse
    props = {}
    for prop_name, prop_value in traverse(mi_obj):
        props[prop_name] = prop_value
    return props

def get_color_strength_from_radiance(radiance):
    # FIXME: Find a proper way of converting radiance to color/energy
    strength = max(radiance)
    if strength < 1.0:
        return radiance, 1.0
    return [c / strength for c in radiance], strength

def linear_rgb_to_luminance(color):
    return 0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2]

###########################
##  Reflectance spectra  ##
###########################

def convert_mi_srgb_reflectance_spectrum(mi_obj, default):
    assert mi_obj.class_().name() == 'SRGBReflectanceSpectrum'
    obj_props = _get_mi_obj_properties(mi_obj)
    return list(obj_props.get('value', default))

#######################
##  Emitter spectra  ##
#######################

def convert_mi_srgb_emitter_spectrum(mi_obj, default):
    assert mi_obj.class_().name() == 'SRGBReflectanceSpectrum'
    obj_props = _get_mi_obj_properties(mi_obj)
    radiance = list(obj_props.get('value', default))
    return get_color_strength_from_radiance(radiance)