
def get_color_strength_from_radiance(radiance):
    # FIXME: Find a proper way of converting radiance to color/energy
    strength = max(radiance)
    if strength < 1.0:
        return radiance, 1.0
    return [c / strength for c in radiance], strength


def convert_radiance_property(mi_context, mi_props, name, default):
    '''Split a radiance-like property (a Color or a Float) into a Blender
    color and a scalar strength.'''
    from mitsuba import Properties
    if name in mi_props:
        prop_type = mi_props.type(name)
        if prop_type == Properties.Type.Color:
            return get_color_strength_from_radiance(list(mi_props[name]))
        if prop_type == Properties.Type.Float:
            return get_color_strength_from_radiance(
                [float(mi_props[name])] * 3)
        mi_context.log(f'Radiance property "{name}" of type {prop_type} is '
                       'not supported. Using the default value.', 'WARN')
    return get_color_strength_from_radiance(list(default))
