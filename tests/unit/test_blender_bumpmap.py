"""The blender_bumpmap texture plugin: agreement with Mitsuba's bumpmap,
finite differences over the ray cone footprint, and footprint requests."""

import sys

import numpy as np
import pytest


@pytest.fixture
def mi(mi_addon):
    import mitsuba as mi
    if 'llvm_ad_rgb' not in mi.variants():
        pytest.skip('llvm_ad_rgb is not available')
    mi.set_variant('llvm_ad_rgb')
    sys.modules[mi_addon].plugins.register_plugins()
    return mi


def height_texture(mi, values):
    return {'type': 'bitmap', 'raw': True, 'filter_type': 'bilinear',
            'bitmap': mi.Bitmap(np.asarray(values, dtype=np.float32)[..., None])}


def make_si(mi, uv, footprint=None):
    import drjit as dr
    si = dr.zeros(mi.SurfaceInteraction3f)
    si.p = mi.Point3f(0, 0, 0)
    si.n = mi.Normal3f(0, 0, 1)
    si.sh_frame = mi.Frame3f(si.n)
    si.dp_du = mi.Vector3f(1, 0, 0)
    si.dp_dv = mi.Vector3f(0, 1, 0)
    si.uv = mi.Point2f(*uv)
    si.wi = dr.normalize(mi.Vector3f(0.3, -0.2, 1))
    if footprint is not None:
        si.footprint = mi.Matrix2f(footprint)
    return si


def eval_bsdf(mi, bsdf, si):
    import drjit as dr
    wo = [dr.normalize(mi.Vector3f(x, y, 1))
          for x, y in ((0, 0), (0.8, 0.1), (-0.5, 0.6), (0.2, -0.9))]
    return np.array([bsdf.eval(mi.BSDFContext(), si, w)[0] for w in wo])


def test_matches_bumpmap_without_footprint(mi):
    rng = np.random.default_rng(1)
    height = height_texture(mi, rng.random((16, 16)))
    ours = mi.load_dict({
        'type': 'normalmap', 'use_shadowing_function': False,
        'normalmap': {'type': 'blender_bumpmap', 'texture': height,
                      'scale': 0.05},
        'bsdf': {'type': 'diffuse'}})
    ref = mi.load_dict({
        'type': 'bumpmap', 'use_shadowing_function': False, 'scale': 0.05,
        'texture': height, 'bsdf': {'type': 'diffuse'}})
    for uv in ((0.31, 0.62), (0.77, 0.14)):
        si = make_si(mi, uv)
        assert np.allclose(eval_bsdf(mi, ours, si), eval_bsdf(mi, ref, si),
                           atol=1e-5)


def test_footprint_filters_detail(mi):
    # Texels alternating along u are invisible to finite differences that
    # step by two texels, while the analytic gradient is steep
    n = 64
    values = np.tile(np.arange(n) % 2, (4, 1))
    tex = mi.load_dict({'type': 'blender_bumpmap', 'scale': 0.1,
                        'texture': height_texture(mi, values)})
    flat = mi.Color3f(0.5, 0.5, 1.0)
    uv = (0.3, 0.5)

    c = tex.eval_3(make_si(mi, uv))
    assert abs(c.x[0] - 0.5) > 0.1

    si = make_si(mi, uv, [[2 / n, 0], [0, 1 / n]])
    assert np.allclose(np.array(tex.eval_3(si)).ravel(), np.array(flat).ravel(),
                       atol=1e-5)

    # A footprint narrowed for jittered sampling is widened back to the pixel
    si = make_si(mi, uv, [[0.5 / n, 0], [0, 0.25 / n]])
    si.footprint_scale = 0.25
    assert np.allclose(np.array(tex.eval_3(si)).ravel(), np.array(flat).ravel(),
                       atol=1e-5)


def test_footprint_matches_smooth_gradient(mi):
    # A linear ramp has the same gradient at any footprint size
    n = 64
    values = np.tile(np.arange(n) / n, (4, 1))
    tex = mi.load_dict({'type': 'blender_bumpmap', 'scale': 0.2,
                        'texture': height_texture(mi, values)})
    uv = (0.4, 0.5)
    analytic = np.array(tex.eval_3(make_si(mi, uv))).ravel()
    fd = np.array(tex.eval_3(make_si(mi, uv, [[4 / n, 1 / n],
                                             [0, 2 / n]]))).ravel()
    assert abs(analytic[0] - 0.5) > 0.05
    assert np.allclose(fd, analytic, atol=1e-3)


def test_position_dependent_height(mi):
    # Procedural textures such as tex_noise read the position instead of
    # the UV coordinates
    class PositionRamp(mi.Texture):
        def eval_1(self, si, active=True):
            return 0.3 * si.p.x

    mi.register_texture('test_position_ramp', PositionRamp)
    tex = mi.load_dict({'type': 'blender_bumpmap', 'scale': 0.5,
                        'texture': {'type': 'test_position_ramp'}})
    m = np.array([-0.15, 0, 1]) / np.linalg.norm([-0.15, 0, 1])
    for footprint in (None, [[0.1, 0], [0, 0.1]]):
        c = tex.eval_3(make_si(mi, (0.5, 0.5), footprint))
        assert np.allclose(np.array(c).ravel(), m * 0.5 + 0.5, atol=1e-5)


def test_strength_and_filter_width(mi):
    rng = np.random.default_rng(2)
    height = height_texture(mi, rng.random((16, 16)))
    si = make_si(mi, (0.45, 0.55), [[0.2, 0], [0, 0.2]])

    tex = mi.load_dict({'type': 'blender_bumpmap', 'texture': height,
                        'scale': 0.3, 'strength': 0.0})
    assert np.allclose(np.array(tex.eval_3(si)).ravel(), [0.5, 0.5, 1.0],
                       atol=1e-6)

    # A zero filter width leaves no footprint and falls back to the analytic
    # gradient
    narrow = mi.load_dict({'type': 'blender_bumpmap', 'texture': height,
                           'scale': 0.3, 'filter_width': 0.0})
    analytic = mi.load_dict({'type': 'blender_bumpmap', 'texture': height,
                             'scale': 0.3})
    assert np.allclose(np.array(narrow.eval_3(si)).ravel(),
                       np.array(analytic.eval_3(make_si(mi, (0.45, 0.55)))).ravel(),
                       atol=1e-5)


def test_scene_requests_footprints(mi):
    import drjit as dr
    rng = np.random.default_rng(3)
    scene = mi.load_dict({
        'type': 'scene',
        'rect': {
            'type': 'rectangle',
            'bsdf': {
                'type': 'normalmap',
                'normalmap': {'type': 'blender_bumpmap',
                              'texture': height_texture(mi, rng.random((8, 8)))},
                'bsdf': {'type': 'diffuse'},
            },
        },
    })
    assert scene.has_filtered_textures()

    ray = mi.Ray3f(mi.Point3f(0.1, 0.2, 3), mi.Vector3f(0, 0, -1))
    ray.cone = mi.RayCone(0.02, 0)
    si = scene.ray_intersect(ray, mi.RayFlags.Default, coherent=True)
    assert np.allclose(np.linalg.svd(np.array(si.footprint).reshape(2, 2),
                                     compute_uv=False), [0.01, 0.01], atol=1e-6)
