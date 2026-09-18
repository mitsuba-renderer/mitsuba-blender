'''Material variants for shapes that shadow rays ignore.

Cycles lets shadow rays pass through an object with ``visible_shadow`` off
while camera and bounce rays hit it. The ``shadowless`` BSDF plugin of this
addon (``plugins/bsdfs/shadowless.py``) does the same in Mitsuba by adding
a null component that shadow rays walk through and that is never sampled,
so a shape gets a wrapped variant of its material. The variant references
the original BSDF, which other shapes keep using as it is.
'''


def shadowless_material(export_ctx, bsdf_id):
    '''Return the id of the ``shadowless`` wrapper around ``bsdf_id``,
    adding it to the scene dict once.'''
    cache = export_ctx.shadowless_materials
    if bsdf_id not in cache:
        variant_id = f'{bsdf_id}-shadowless'
        export_ctx.data_add({'type': 'shadowless',
                             'bsdf': export_ctx.create_ref(bsdf_id)},
                            variant_id)
        cache[bsdf_id] = variant_id
    return cache[bsdf_id]


def is_shadowless(export_ctx, bsdf_id):
    '''Whether the material ``bsdf_id`` is a ``shadowless`` BSDF, possibly
    inside twosided or normal map wrappers.'''
    params = export_ctx.data_get(bsdf_id)
    while isinstance(params, dict):
        kind = params.get('type')
        if kind == 'shadowless':
            return True
        if kind not in ('twosided', 'normalmap'):
            return False
        params = params.get('bsdf')
    return False
