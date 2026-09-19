
def _register_all():
    import mitsuba as mi
    import drjit as dr

    from .textures import blender_bumpmap, tex_noise
    from .shapes import cycles_lights
    from .bsdfs import shadowless

    blender_bumpmap.register(mi, dr)
    tex_noise.register(mi, dr)
    cycles_lights.register(mi, dr)
    shadowless.register(mi, dr)


def register_plugins():
    '''Called by the Blender addon after set_variant.'''
    _register_all()


# Entry-point auto-discovery: Mitsuba imports this module after
# set_variant and reloads it on every variant change.
import mitsuba as mi
if mi.variant() is not None:
    _register_all()
