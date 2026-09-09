'''Material variants for shapes that only camera rays can see.

The camera ray keeps its visibility class through specular events, so it
refracts at every camera-only pane along its way. The replacement keeps the
``eta_scale`` flag of the original lobe, so it matches Cycles by leaving
out the 1 / eta^2 radiance scale.

The principled refraction is a glossy lobe even at roughness zero, and only
a delta lobe keeps the camera class, so a smooth, fully transmissive
``principled`` lobe is replaced by a ``dielectric``.
'''
from .textures import _math

# Principled roughness up to which the refraction counts as smooth
_SMOOTH_ROUGHNESS = 0.1


def _sqrt(value):
    '''Square root of a spectrum-like parameter'''
    if value is None:
        return 1.0
    if isinstance(value, (int, float)):
        return value ** 0.5
    if isinstance(value, dict) and value.get('type') == 'rgb':
        v = value['value']
        if isinstance(v, (int, float)):
            return {'type': 'rgb', 'value': v ** 0.5}
        return {'type': 'rgb', 'value': [c ** 0.5 for c in v]}
    return _math('sqrt(in[0])', value)


def _copy(value):
    '''Copy the dict and list structure of a plugin dict. Leaves such as
    Mitsuba transforms are shared, which is fine since nothing mutates
    them.'''
    if isinstance(value, dict):
        return {k: _copy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_copy(v) for v in value]
    return value


def _smooth(value):
    '''Whether a roughness parameter is at most the smooth limit; textured
    values count as smooth'''
    return not isinstance(value, (int, float)) or value <= _SMOOTH_ROUGHNESS


def _to_dielectric(params, log):
    '''Walk a BSDF dict and replace every smooth, fully transmissive
    principled lobe by a dielectric. Returns whether anything changed.'''
    if not isinstance(params, dict):
        return False
    if params.get('type') == 'principled':
        spec_trans = params.get('spec_trans', 0.0)
        if isinstance(spec_trans, (int, float)) and spec_trans >= 1.0 - 1e-6:
            eta = params.get('eta', 1.5)
            metallic = params.get('metallic', 0.0)
            if not isinstance(eta, (int, float)) or metallic != 0.0:
                log('a principled glass with a textured eta or with '
                    'metallic keeps its glossy refraction')
            elif _smooth(params.get('roughness')):
                # The principled transmission carries sqrt(base_color) per
                # interface, as the dielectric's transmittance does
                transmittance = _sqrt(params.get('base_color'))
                eta_scale = params.get('eta_scale', True)
                params.clear()
                params.update({'type': 'dielectric', 'int_ior': eta,
                               'ext_ior': 1.0, 'eta_scale': eta_scale,
                               'specular_transmittance': transmittance})
                return True
            else:
                log('a rough principled glass keeps its glossy refraction')
    changed = False
    for value in params.values():
        if isinstance(value, dict) and 'type' in value:
            changed |= _to_dielectric(value, log)
    return changed


def refractive(export_ctx, mat_id):
    '''Whether the material has a lobe that refracts'''
    def walk(params):
        if not isinstance(params, dict):
            return False
        kind = params.get('type')
        if kind in ('dielectric', 'roughdielectric', 'thindielectric'):
            return True
        if kind == 'principled':
            spec_trans = params.get('spec_trans', 0.0)
            if isinstance(spec_trans, dict) or spec_trans > 0.0:
                return True
        return any(walk(v) for v in params.values()
                   if isinstance(v, dict) and 'type' in v)

    return walk(export_ctx.data_get(mat_id))


def primary_material(export_ctx, mat_id):
    '''Return the id of the material to use on a shape that only camera
    rays see: a copy of ``mat_id`` with its smooth principled refraction
    made a dielectric, or ``mat_id`` itself when it has none.'''
    params = export_ctx.data_get(mat_id)
    if not isinstance(params, dict):
        return mat_id
    cache = export_ctx.primary_materials
    if mat_id in cache:
        return cache[mat_id]
    variant_id = f'{mat_id}-primary'
    messages = []
    variant = _copy(params)
    if _to_dielectric(variant, messages.append):
        export_ctx.data_add(variant, variant_id)
        cache[mat_id] = variant_id
    else:
        cache[mat_id] = mat_id
    for msg in messages:
        export_ctx.log(f'Material "{mat_id}" on a camera-only object: {msg}, '
                       'so the camera ray becomes a secondary ray behind it.',
                       'WARN')
    return cache[mat_id]
