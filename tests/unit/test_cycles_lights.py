"""The cycles_lights shape plugin: sampling, intersection and radiometry
against Cycles' formulas."""

import math
import sys

import numpy as np
import pytest


@pytest.fixture(scope='session')
def plugins(mi_addon):
    return sys.modules[mi_addon].plugins


def variant_with_wavefront():
    import mitsuba as mi
    for v in ('llvm_ad_rgb', 'llvm_rgb', 'cuda_ad_rgb'):
        if v in mi.variants():
            return v
    return None


def set_wavefront_variant(plugins):
    import mitsuba as mi
    variant = variant_with_wavefront()
    if variant is None:
        pytest.skip('no wavefront variant available')
    mi.set_variant(variant)
    plugins.register_plugins()


def two_lights(power=100.0, radius=0.25, selection='importance'):
    """A point light at the origin and a spot light off to the side."""
    return {
        'type': 'cycles_lights',
        'light_selection': selection,
        'p0': [0, 0, 0], 'r0': radius,
        'power0': {'type': 'rgb', 'value': power},
        'p1': [5, 0, 0], 'r1': 0.5, 'power1': 30.0,
        'dir1': [0, 0, 1], 'angle1': 60.0, 'blend1': 0.2,
    }


SELECTIONS = ('uniform', 'importance')


@pytest.mark.parametrize('selection', SELECTIONS)
def test_irradiance_matches_cycles(plugins, selection):
    """A receiver on the axis of a light sees P / (4 pi (d^2 + r^2)) from
    the oriented disk whichever way the light is chosen, and the sampling
    routines agree with each other."""
    import mitsuba as mi
    import drjit as dr
    set_wavefront_variant(plugins)

    power, radius, d = 100.0, 0.25, 1.0
    # Endpoints refer to their shape without owning it
    shape = mi.load_dict(two_lights(power, radius, selection))
    emitter = shape.emitter()
    n = 200000
    it = dr.zeros(mi.Interaction3f, n)
    it.p = mi.Point3f(0, 0, d)
    sampler = mi.load_dict({'type': 'independent'})
    sampler.seed(0, n)
    ds, weight = emitter.sample_direction(it, sampler.next_2d())

    # The samples of the first light, each weighted by its selection
    # probability
    first = np.array(ds.uv.x) == 0
    cos_receiver = np.array(dr.dot(ds.d, mi.Vector3f(0, 0, -1)))
    irradiance = (np.array(weight[0]) * cos_receiver)[first].sum() / n
    expected = power / (4 * math.pi * (d * d + radius * radius))
    assert irradiance == pytest.approx(expected, rel=5e-3)

    # No sample lies closer than the light center
    assert np.array(ds.dist)[first].min() >= d - 1e-5

    assert np.allclose(np.array(emitter.pdf_direction(it, ds)),
                       np.array(ds.pdf), rtol=1e-5)
    assert np.allclose(np.array(emitter.eval_direction(it, ds)[0])
                       / np.array(ds.pdf), np.array(weight[0]), rtol=1e-5)
    assert not bool(dr.any(ds.delta, axis=None))


def test_hits_are_consistent_with_sampling(plugins):
    """A BSDF-sampled ray hits the disk facing its origin, sees the same
    radiance as emitter sampling, and the scene reports the density that
    emitter sampling would have used (the basis of MIS)."""
    import mitsuba as mi
    import drjit as dr
    set_wavefront_variant(plugins)

    power, radius = 100.0, 0.25
    scene = mi.load_dict({'type': 'scene',
                          'lights': two_lights(power, radius, 'uniform')})
    assert len(scene.shapes()) == 1
    assert scene.shapes()[0].primitive_count() == 2
    assert scene.has_null_shapes()

    ref = dr.zeros(mi.Interaction3f, 1)
    ref.p = mi.Point3f(0.1, 0.05, 1.0)
    target = mi.Point3f(0.05, 0.0, 0.0)
    ray = mi.Ray3f(ref.p, dr.normalize(target - ref.p))
    si = scene.ray_intersect(ray)
    assert dr.all(si.is_valid())
    assert dr.allclose(si.emitter(scene).eval(si),
                       power / (4 * math.pi ** 2 * radius ** 2))

    ds = mi.DirectionSample3f(scene, si, ref)
    disk_normal = dr.normalize(ref.p - mi.Point3f(0, 0, 0))
    cos_l = dr.dot(disk_normal, -ds.d)
    expected_pdf = dr.square(ds.dist) / (math.pi * radius ** 2 * cos_l) / 2
    assert dr.allclose(scene.pdf_emitter_direction(ref, ds), expected_pdf,
                       rtol=1e-4)

    # Shadow rays pass through lights, and a ray that misses the disk
    # continues
    assert dr.all(scene.ray_test_tr(ray) == 1, axis=None)
    beside = mi.Ray3f(mi.Point3f(0.3, 0, 1), mi.Vector3f(0, 0, -1))
    assert not dr.any(scene.ray_intersect(beside).is_valid())


def test_receiver_within_the_radius(plugins):
    """A ray that starts within a light's radius misses it, which keeps a
    path that crossed the light from hitting it a second time. The light
    samples of such a receiver are delta samples that carry the exact
    irradiance."""
    import mitsuba as mi
    import drjit as dr
    set_wavefront_variant(plugins)

    power, radius = 100.0, 0.25
    scene = mi.load_dict({'type': 'scene',
                          'lights': two_lights(power, radius, 'uniform')})
    origin = mi.Point3f(0.1, 0.05, 1.0)
    ray = mi.Ray3f(origin, dr.normalize(mi.Point3f(0.05, 0, 0) - origin))
    si = scene.ray_intersect(ray)
    assert dr.all(si.is_valid())
    # The path continues from the disk, and nothing else lies ahead
    assert not dr.any(scene.ray_intersect(si.spawn_ray(ray.d)).is_valid())
    inside = mi.Ray3f(mi.Point3f(0.1, 0, 0), mi.Vector3f(-1, 0, 0))
    assert not dr.any(scene.ray_intersect(inside).is_valid())

    d = 0.1
    n = 200000
    it = dr.zeros(mi.Interaction3f, n)
    it.p = mi.Point3f(0, 0, d)
    sampler = mi.load_dict({'type': 'independent'})
    sampler.seed(0, n)
    emitter = scene.shapes()[0].emitter()
    ds, weight = emitter.sample_direction(it, sampler.next_2d())
    first = np.array(ds.uv.x) == 0
    delta = np.array(ds.delta)
    assert np.all(delta[first]) and not np.any(delta[~first])
    cos_receiver = np.array(dr.dot(ds.d, mi.Vector3f(0, 0, -1)))
    irradiance = (np.array(weight[0]) * cos_receiver)[first].sum() / n
    expected = power / (4 * math.pi * (d * d + radius * radius))
    assert irradiance == pytest.approx(expected, rel=5e-3)


def test_light_selection(plugins):
    """Importance selection picks a light in proportion to the irradiance
    it would produce, and hits report the matching density."""
    import mitsuba as mi
    import drjit as dr
    set_wavefront_variant(plugins)

    def lights(selection):
        # One cluster, so that the selection is exactly proportional to the
        # per-light estimate
        return {
            'type': 'cycles_lights', 'light_selection': selection,
            'cluster_count': 1,
            'p0': [0, 0, 0], 'r0': 0.25, 'power0': 100.0,
            'p1': [0, 3, 0], 'r1': 0.1, 'power1': 400.0,
            'p2': [2, 0, 0], 'r2': 0.5, 'power2': 50.0,
        }

    p = mi.Point3f(0, 0, 1)
    weights = []
    for center, radius, power in ([0, 0, 0], 0.25, 100.0), \
                                 ([0, 3, 0], 0.1, 400.0), \
                                 ([2, 0, 0], 0.5, 50.0):
        d2 = sum((a - b) ** 2 for a, b in zip(center, [0, 0, 1]))
        weights.append(power / (4 * math.pi * (d2 + radius ** 2)))
    expected = np.array(weights) / sum(weights)

    n = 400000
    it = dr.zeros(mi.Interaction3f, n)
    it.p = p
    shape = mi.load_dict(lights('importance'))
    sampler = mi.load_dict({'type': 'independent'})
    sampler.seed(0, n)
    ds, weight = shape.emitter().sample_direction(it, sampler.next_2d())
    k = np.array(ds.uv.x)
    frequencies = np.array([(k == j).mean() for j in range(3)])
    assert np.allclose(np.array(shape.emitter().pdf_direction(it, ds)),
                       np.array(ds.pdf), rtol=1e-4)
    assert not np.any(np.array(ds.pdf) == 0)
    assert np.allclose(frequencies, expected, atol=0.005)

    # The density of a BSDF-sampled hit includes the selection probability
    scene = mi.load_dict({'type': 'scene', 'lights': lights('importance')})
    ref = dr.zeros(mi.Interaction3f, 1)
    ref.p = p
    ray = mi.Ray3f(p, mi.Vector3f(0, 0, -1))
    si = scene.ray_intersect(ray)
    ds = mi.DirectionSample3f(scene, si, ref)
    pdf = scene.pdf_emitter_direction(ref, ds)
    assert dr.allclose(pdf, expected[0] / (math.pi * 0.25 ** 2), rtol=1e-4)


def test_many_lights(plugins):
    """With many lights the selection sweeps the cluster nodes of the tree:
    every light is found by a ray aimed at it, the density of a sampled
    light equals the density that the hit-side replay of the cluster and
    light sweeps reports, and the frequencies of the chosen lights at one
    point match the replayed probabilities."""
    import mitsuba as mi
    import drjit as dr
    set_wavefront_variant(plugins)

    rng = np.random.default_rng(7)
    n = 200
    lights = {'type': 'cycles_lights', 'leaf_size': 4}
    centers = rng.uniform(-5, 5, size=(n, 3))
    for i in range(n):
        lights[f'p{i}'] = centers[i].tolist()
        lights[f'r{i}'] = float(rng.uniform(0.05, 0.3))
        lights[f'power{i}'] = float(rng.uniform(1, 100))
        if i % 3:
            d = rng.normal(size=3)
            lights[f'dir{i}'] = (d / np.linalg.norm(d)).tolist()
            lights[f'angle{i}'] = float(rng.uniform(10, 120))
            lights[f'blend{i}'] = float(rng.uniform(0, 1))
    scene = mi.load_dict({'type': 'scene', 'lights': lights})
    shape = scene.shapes()[0]
    emitter = shape.emitter()
    assert shape.primitive_count() == n
    assert 'nodes=127, leaves=64, clusters=16' in str(shape)

    # Every light is found by a ray aimed at it, and a hit that receives
    # emission reports a density with which emitter sampling reaches it
    ref = dr.zeros(mi.Interaction3f, n)
    ref.p = mi.Point3f(0.3, -0.2, 0.1)
    targets = mi.Point3f(*[mi.Float(c) for c in centers.T])
    ray = mi.Ray3f(ref.p, dr.normalize(targets - ref.p))
    si = scene.ray_intersect(ray)
    assert dr.all(si.is_valid())
    ds_hit = mi.DirectionSample3f(scene, si, ref)
    pdf_hit = np.array(scene.pdf_emitter_direction(ref, ds_hit))
    lit = np.array(dr.sum(si.emitter(scene).eval(si))) > 0
    # Every third light is a point light and always lit
    assert lit.sum() >= n // 3
    assert np.array_equal(pdf_hit > 0, lit)

    m = 500000
    sampler = mi.load_dict({'type': 'independent'})
    sampler.seed(1, m)
    it = dr.zeros(mi.Interaction3f, m)
    it.p = mi.Point3f(sampler.next_1d() * 12 - 6, sampler.next_1d() * 12 - 6,
                      sampler.next_1d() * 12 - 6)
    ds, weight = emitter.sample_direction(it, sampler.next_2d())
    pdf = np.array(ds.pdf)
    # A chosen cluster whose lights all face away yields no sample; the
    # replay reports zero for those
    valid = pdf > 0
    assert valid.mean() > 0.9
    replay = np.array(emitter.pdf_direction(it, ds))
    assert np.allclose(replay[valid], pdf[valid], rtol=1e-4)
    assert np.all(replay[~valid] == 0)

    p = mi.Point3f(0.5, -1.0, 0.3)
    it = dr.zeros(mi.Interaction3f, m)
    it.p = p
    sampler.seed(2, m)
    ds, weight = emitter.sample_direction(it, sampler.next_2d())
    k = np.array(ds.uv.x).astype(int)
    pdf = np.array(ds.pdf)
    frequencies = np.bincount(k[pdf > 0], minlength=n) / m
    # The replayed probability of every light (internal order), through a
    # direction to the light center where the disk faces the point
    records = np.array(shape.records).reshape(-1, 16)
    centers = mi.Point3f(*[mi.Float(c) for c in records[:, :3].T])
    ref = dr.zeros(mi.Interaction3f, n)
    ref.p = p
    ds = dr.zeros(mi.DirectionSample3f, n)
    ds.uv = mi.Point2f(mi.Float(np.arange(n, dtype=np.float32)), 0)
    ds.d = dr.normalize(centers - p)
    ds.dist = dr.norm(centers - p)
    pmf = np.array(emitter.pdf_direction(ref, ds)) * math.pi \
        * records[:, 3] ** 2 / np.array(ds.dist) ** 2
    assert pmf.sum() == pytest.approx((pdf > 0).mean(), abs=2e-3)
    assert np.abs(frequencies - pmf).max() < 4 * math.sqrt(pmf.max() / m)


def test_hit_radiance(plugins):
    """A ray that hits a light sees the radiance of Cycles' disk light,
    P / (pi * 4 pi r^2) per channel."""
    import mitsuba as mi
    import drjit as dr
    set_wavefront_variant(plugins)

    power, radius = 100.0, 0.25
    ray = mi.Ray3f(mi.Point3f(0.05, 0.0, 1.0), mi.Vector3f(0, 0, -1))
    scene = mi.load_dict({'type': 'scene', 'lights': two_lights(power, radius)})
    si = scene.ray_intersect(ray)
    assert dr.allclose(dr.sum(si.emitter(scene).eval(si)),
                       3 * power / (4 * math.pi ** 2 * radius ** 2))


def test_spot_falloff(plugins):
    """Cycles attenuates a spot light with a smoothstep of the cosine to
    the axis, scaled by the blend."""
    import mitsuba as mi
    set_wavefront_variant(plugins)

    angle, blend, power, radius = 60.0, 0.2, 30.0, 0.5
    scene = mi.load_dict({'type': 'scene', 'lights': two_lights()})
    cos_half = math.cos(math.radians(angle / 2))
    smooth = 1 / ((1 - cos_half) * blend)
    for theta in (0.0, 25.0, 28.0, 35.0):
        t = math.radians(theta)
        # A ray towards the spot light center, at angle theta to its axis
        d = mi.Vector3f(-math.sin(t), 0, -math.cos(t))
        ray = mi.Ray3f(mi.Point3f(5, 0, 0) - 3 * d, d)
        si = scene.ray_intersect(ray)
        assert bool(si.is_valid()[0])
        x = min(max((math.cos(t) - cos_half) * smooth, 0.0), 1.0)
        expected = power / (4 * math.pi ** 2 * radius ** 2) * x * x * (3 - 2 * x)
        assert si.emitter(scene).eval(si)[0][0] == pytest.approx(expected,
                                                                  rel=1e-4)


def test_render_under_the_light(plugins):
    """A diffuse floor right under the light receives E / pi * albedo."""
    import mitsuba as mi
    mi.set_variant('scalar_rgb')
    plugins.register_plugins()
    power, radius, height = 100.0, 0.25, 1.0
    scene = mi.load_dict({
        'type': 'scene',
        'integrator': {'type': 'path', 'max_depth': 2},
        'sensor': {
            'type': 'orthographic',
            'to_world': mi.ScalarTransform4f().look_at(
                [0, 0, 5], [0, 0, 0], [0, 1, 0]).scale([0.05, 0.05, 1]),
            'film': {'type': 'hdrfilm', 'width': 4, 'height': 4,
                     'rfilter': {'type': 'box'}},
            'sampler': {'type': 'independent'},
        },
        'floor': {'type': 'rectangle', 'to_world': mi.ScalarTransform4f().scale(2),
                  'bsdf': {'type': 'diffuse'}},
        'light': {'type': 'cycles_lights', 'p0': [0, 0, height], 'r0': radius,
                  'power0': {'type': 'rgb', 'value': power},
                  'visibility': 'secondary'},
    })
    img = np.array(mi.render(scene, spp=256, seed=0))
    expected = power / (4 * math.pi * (height ** 2 + radius ** 2)) / math.pi * 0.5
    assert img[..., 0].mean() == pytest.approx(expected, rel=0.03)


def test_kernels_do_not_depend_on_the_light_count(plugins):
    """The numbers of lights and tree nodes are opaque: the same kernel
    serves any count. (Dr.Jit switches to packet loads for arrays of 32
    floats or more, so both counts need at least two nodes. The LLVM
    backend occasionally emits a kernel that differs by one operation for
    identical inputs, so the counts are compared over a few repetitions.)"""
    import mitsuba as mi
    import drjit as dr
    set_wavefront_variant(plugins)

    def hashes(count):
        lights = {'type': 'cycles_lights'}
        for i in range(count):
            lights[f'p{i}'] = [i, 0, 0]
            lights[f'r{i}'] = 0.1
            lights[f'power{i}'] = 1.0 + i
        scene = mi.load_dict({'type': 'scene', 'lights': lights})
        ray = mi.Ray3f(mi.Point3f(0, 0, 1), mi.Vector3f(0, 0, -1))
        it = dr.zeros(mi.Interaction3f, 2)
        it.p = mi.Point3f(0, 0, 1)
        with dr.scoped_set_flag(dr.JitFlag.KernelHistory, True):
            si = scene.ray_intersect(ray)
            ds, spec = scene.sample_emitter_direction(it, mi.Point2f(0.3, 0.6),
                                                      False)
            dr.eval(si.t, ds.pdf, spec)
            return tuple(k['hash'] for k in dr.kernel_history()
                         if k['type'] == dr.KernelType.JIT)

    small = {hashes(20) for _ in range(3)}
    large = {hashes(200) for _ in range(3)}
    assert small & large
