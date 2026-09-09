import re

import bpy


def sanitize_attribute_name(name):
    '''Mesh attribute names as exported to Mitsuba, shared between the
    mesh exporter and the Color Attribute texture converter so that
    mesh_attribute references match the exported attributes.'''
    return re.sub(r'\W', '_', name)


def visibility_class(primary, secondary):
    '''Mitsuba ``visibility`` value for something that primary (camera)
    and/or secondary rays can see, or None when neither can.'''
    if primary and secondary:
        return 'all'
    if primary:
        return 'primary'
    if secondary:
        return 'secondary'
    return None


def ray_visibility(b_object, emissive):
    '''Mitsuba ``visibility`` value of a Blender object, derived from its
    Cycles ray visibility flags. Returns None when no supported ray type
    sees the object, in which case it can be left out of the scene.

    Mitsuba distinguishes primary (camera) rays from secondary rays, which
    cover Cycles' diffuse, glossy, transmission and shadow rays at once. An
    object is secondary when any of those ray types sees it, except that
    shadow rays alone do not make an emissive object secondary, since they
    never reach a light source. The shadow flag is not expressible on its
    own: an object that bounce rays see but shadow rays ignore keeps its
    bounce visibility, unless its material refracts, in which case the mesh
    exporter makes it camera-only (see ``materials.primary``). ``emissive``
    should be False for Blender lights only when they emit nothing.

    When refractive caustics are off, Cycles drops transmission closures
    after a diffuse bounce, and transmission rays only reach an emissive
    object on paths that start at the camera. Mitsuba keeps the primary
    ray mask through delta scattering. A camera-visible emitter that other
    rays only see through transmission (e.g. a backdrop behind camera-only
    window glass) is therefore ``primary``.
    '''
    transmission = b_object.visible_transmission
    if emissive and b_object.visible_camera and not _refractive_caustics():
        transmission = False
    secondary = b_object.visible_diffuse or b_object.visible_glossy \
        or transmission
    if not emissive:
        secondary = secondary or b_object.visible_shadow
    return visibility_class(b_object.visible_camera, secondary)


def _refractive_caustics():
    # scene.cycles only exists while the Cycles addon is enabled
    cycles = getattr(bpy.context.scene, 'cycles', None)
    return cycles is None or cycles.caustics_refractive
