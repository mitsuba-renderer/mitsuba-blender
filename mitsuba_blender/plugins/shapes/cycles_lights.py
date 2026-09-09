'''Blender point and spot lights with a radius, following Cycles.

Cycles samples such a light as a disk of the light's radius, centered on the
light and facing the point being shaded, and intersects the same disk (facing
the ray origin) along BSDF-sampled rays so that both strategies can be
combined with multiple importance sampling. The light radiates
``power / (4 pi^2 radius^2)``, never occludes anything, and spot lights
attenuate the emission with Cycles' smoothstep falloff. This corresponds to
Blender's "Soft Falloff" setting, which is the default.

The ``cycles_lights`` shape holds every such light of a scene as one
primitive each, so that kernels do not depend on the number of lights. Each
primitive enters the acceleration data structure with the bounding box of
the light's sphere, and Mitsuba compiles the disk intersection of a
primitive from ``ray_intersect_preliminary()``. The records of all lights
live in one flat array of 16 floats per light, which the kernels read with
packet loads. The shape attaches the ``cycles_lights_emitter`` emitter and a
``null`` BSDF unless told otherwise, so that shadow rays pass through a
light and paths continue through it like in Cycles.

Cycles continues a ray that hit a light from the same origin. The light's
disk keeps facing that origin and is not hit again. Mitsuba instead
continues the path from the hit point, and the disk that faces this new
origin would be hit a second time. The shape therefore ignores hits of a
light along rays that start within its radius. Since BSDF sampling cannot
reach such a light, the light samples of a receiver within the radius are
marked as delta samples, which gives them the full weight.

Lights are numbered from zero, and the shape reads properties until the
first missing position:

  p<i> (point): light center
  r<i> (float): radius, must be positive
  power<i> (rgb or float): radiant power times color. Default 1
  dir<i> (vector): emission axis of a spot light. Point light if absent
  angle<i> (float): full cone angle of a spot light in degrees. Default 45
  blend<i> (float): Blender's spot blend, the softness of the cone edge.
    Default 0.15

The ``visibility`` property of the shape applies to all of its lights. The
emitter's sampling weight defaults to the number of lights, so that the
scene chooses the shape as often as it would choose that many separate
emitters. RGB variants only.

At load time the lights are arranged in a binary tree by recursive median
splits of their centers, with up to ``leaf_size`` (integer, default 8)
lights per leaf. Each node carries a bounding sphere, the summed power of
its lights and a cone that bounds their emission axes, like the light tree
of Cycles (Conty and Kulla, "Importance Sampling of Many Lights with
Adaptive Tree Splitting", 2018). The tree serves the selection of a light
for emitter sampling.

Emitter sampling first chooses a light, then a point on its disk. The
``light_selection`` property (string) sets the choice of the light:

  uniform: every light with the same probability, as Cycles does without
    its light tree
  importance (default): proportional to the unoccluded irradiance that the
    light would produce at the shading point, ``P / (4 pi (d^2 + r^2))``
    times the spot falloff. The choice goes through two flat sweeps: one
    over the ``cluster_count`` (integer, rounded to a power of two, default
    about the square root of the light count) tree nodes at a fixed depth,
    which partition the lights into contiguous ranges, and one over the
    lights of the chosen node. Each sweep turns the estimates into a choice
    by weighted reservoir sampling. A node's estimate is its summed power
    over the squared distance to its sphere center (at least half the
    sphere radius, as in Cycles), times the cosine of the smallest angle
    that a light of the node can form between its axis and the direction
    to the point, and zero when the node's cone cannot reach the point.
    The pdf of a light for a BSDF-sampled hit replays both sweeps.

Flat sweeps rather than a descent from the root: on the GPU, all lanes
walk the same node list with uniform control flow, which measured faster
than a per-lane descent through the tree up to about a thousand lights.
'''
import math

import numpy as np

# Per light: center (3), radius, radiance (3), spot flag, spot axis (3),
# cos(half angle), spot smoothness, cluster node, weight numerator, unused
STRIDE = 16
# Per node: bounding sphere center (3) and radius, summed weight numerator,
# cone axis (3), cone angle theta_o, emission angle theta_e, right child
# (zero for a leaf; the left child follows the node), unused, first light,
# light count, unused (2)
NSTRIDE = 16

# A small angular margin keeps the cone bounds conservative under float32
CONE_MARGIN = 1e-3


def light_cone(rec):
    '''Bounding cone (axis, theta_o, theta_e) of one light, in Cycles' terms:
    the emission axes lie within theta_o of the axis and each light emits
    within theta_e of its own axis.'''
    if rec[7] > 0.5:
        theta_e = math.acos(max(min(rec[11], 1.0), -1.0))
        return np.array(rec[8:11]), 0.0, theta_e + CONE_MARGIN
    return np.array([0.0, 0.0, 1.0]), math.pi, math.pi / 2


def merge_cones(a, b):
    '''Smallest cone that contains two cones (Cycles' light_tree.cpp)'''
    if b[1] > a[1]:
        a, b = b, a
    axis_a, theta_oa, theta_ea = a
    axis_b, theta_ob, theta_eb = b
    cos_ab = float(np.clip(np.dot(axis_a, axis_b), -1.0, 1.0))
    theta_d = math.acos(cos_ab)
    theta_e = max(theta_ea, theta_eb)
    if theta_oa + 5e-4 >= min(math.pi, theta_d + theta_ob):
        return axis_a, theta_oa, theta_e
    theta_o = (theta_d + theta_oa + theta_ob) / 2
    if theta_o >= math.pi:
        return axis_a, math.pi, theta_e
    if cos_ab < -0.9995:
        # Opposite axes: any orthogonal direction serves as the new axis
        helper = np.array([1.0, 0.0, 0.0] if abs(axis_a[0]) < 0.9
                          else [0.0, 1.0, 0.0])
        ortho = np.cross(axis_a, helper)
        ortho /= np.linalg.norm(ortho)
    else:
        ortho = axis_b - axis_a * cos_ab
        ortho /= np.linalg.norm(ortho)
    theta_r = theta_o - theta_oa
    axis = axis_a * math.cos(theta_r) + ortho * math.sin(theta_r)
    return axis, theta_o, theta_e


def build_tree(data, leaf_size):
    '''Binary tree over the light records by recursive median splits along
    the widest axis. Returns the light permutation (leaf order) and the
    node records in depth-first order.'''
    cones = [light_cone(rec) for rec in data]
    nodes = []
    order = []

    def build(idx):
        node = len(nodes)
        nodes.append(None)
        centers, radii = data[idx, :3], data[idx, 3]
        lo = (centers - radii[:, None]).min(axis=0)
        hi = (centers + radii[:, None]).max(axis=0)
        center = (lo + hi) / 2
        bound = float((np.linalg.norm(centers - center, axis=1) + radii).max())
        energy = float(data[idx, 14].sum())
        first = len(order)
        if len(idx) <= leaf_size:
            cone = cones[idx[0]]
            for i in idx[1:]:
                cone = merge_cones(cone, cones[i])
            order.extend(idx)
            right = 0
        else:
            axis = np.argmax(np.ptp(centers, axis=0))
            idx = idx[np.argsort(centers[:, axis], kind='stable')]
            half = len(idx) // 2
            cone_l = build(idx[:half])
            right = len(nodes)
            cone_r = build(idx[half:])
            cone = merge_cones(cone_l, cone_r)
        nodes[node] = list(center) + [bound, energy] + list(cone[0]) \
            + [cone[1], cone[2], right, 0, first, len(idx), 0, 0]
        return cone

    build(np.arange(len(data)))
    return np.array(order), np.array(nodes, dtype=np.float32)


def nodes_at_depth(nodes, depth):
    '''Indices of the nodes at ``depth`` and of the leaves above it, which
    together partition the lights into contiguous ranges'''
    result = []

    def collect(node, d):
        right = int(nodes[node, 10])
        if d == depth or right == 0:
            result.append(node)
        else:
            collect(node + 1, d + 1)
            collect(right, d + 1)

    collect(0, 0)
    return np.array(result)


def register(mi, dr):
    scalar = mi.variant().startswith('scalar')

    def emitter_ptr(emitter):
        return emitter if scalar else mi.EmitterPtr(emitter)

    def smoothstep(x):
        x = dr.clip(x, 0.0, 1.0)
        return dr.square(x) * (3.0 - 2.0 * x)

    def zeros(cls):
        # Scalar variants cannot zero-initialize records with a bool field
        return cls() if scalar else dr.zeros(cls)

    def read_light(props, i):
        center = list(props[f'p{i}'])
        radius = float(props[f'r{i}'])
        if radius <= 0.0:
            raise RuntimeError(f'cycles_lights: light {i} needs a positive '
                               'radius')
        power = props.get(f'power{i}', 1.0)
        power = list(power) if hasattr(power, '__len__') else [power] * 3
        radiance = [float(c) / (4.0 * math.pi ** 2 * radius ** 2)
                    for c in power]
        spot = f'dir{i}' in props
        axis, cos_half, smooth = [0.0, 0.0, 0.0], 0.0, 0.0
        if spot:
            axis = np.array(list(props[f'dir{i}']), dtype=np.float64)
            axis = list(axis / np.linalg.norm(axis))
            angle = math.radians(float(props.get(f'angle{i}', 45.0)))
            blend = float(props.get(f'blend{i}', 0.15))
            cos_half = math.cos(angle / 2.0)
            # Cycles: spot_smooth = 1 / ((1 - cos_half) * blend), a hard
            # edge when the blend is zero
            denom = (1.0 - cos_half) * blend
            smooth = 1.0 / denom if denom > 0.0 else 1e30
        # The importance of a light is its weight numerator over the
        # squared distance: (sum of the radiance) * r^2 = P / (4 pi^2)
        numerator = sum(radiance) * radius ** 2
        return center + [radius] + radiance + [1.0 if spot else 0.0] \
            + axis + [cos_half, smooth, 0.0, numerator, 0.0]

    class CyclesLights(mi.Shape):
        def __init__(self, props):
            if mi.is_spectral:
                raise RuntimeError('cycles_lights: only RGB variants are '
                                   'supported')
            records = []
            i = 0
            while f'p{i}' in props:
                records.append(read_light(props, i))
                i += 1
            if i == 0:
                raise RuntimeError('cycles_lights: no light given (the '
                                   'properties p0, r0, .. are missing)')

            if 'emitter' not in props:
                # The scene picks emitters by their sampling weight, so the
                # shape should be picked as often as its lights would be
                # as individual emitters
                props['emitter'] = mi.load_dict(
                    {'type': 'cycles_lights_emitter', 'sampling_weight': i})
            if 'bsdf' not in props:
                props['bsdf'] = mi.load_dict({'type': 'null'})
            mi.Shape.__init__(self, props)
            self.selection = str(props.get('light_selection', 'importance'))
            if self.selection not in ('uniform', 'importance'):
                raise RuntimeError('cycles_lights: unknown light_selection '
                                   f'"{self.selection}"')
            leaf_size = int(props.get('leaf_size', 8))
            if leaf_size < 1:
                raise RuntimeError('cycles_lights: leaf_size must be positive')

            data = np.array(records, dtype=np.float64)
            self.n = len(records)
            order, nodes = build_tree(data, leaf_size)
            data = data[order]
            clusters = int(props.get('cluster_count', 0))
            if clusters > 0:
                depth = round(math.log2(clusters))
            elif self.n >= 4:
                depth = math.ceil(math.log2(math.sqrt(self.n)))
            else:
                depth = 0
            clusters = nodes_at_depth(nodes, depth)
            for c in clusters:
                first, count = int(nodes[c, 12]), int(nodes[c, 13])
                data[first:first + count, 13] = c
            data = data.astype(np.float32)

            self.count = dr.opaque(mi.UInt32, self.n)
            self.cluster_count = dr.opaque(mi.UInt32, len(clusters))
            if scalar:
                self.records, self.nodes = data.ravel(), nodes.ravel()
                self.clusters = clusters.astype(np.uint32)
            else:
                self.records = mi.Float(data.ravel())
                self.nodes = mi.Float(nodes.ravel())
                self.clusters = mi.UInt32(clusters.astype(np.uint32))
            self.n_nodes = len(nodes)
            self.n_leaves = int((nodes[:, 10] == 0).sum())
            self.n_clusters = len(clusters)
            # The disk of a light lies within its sphere whichever way it faces
            centers, radii = data[:, :3], data[:, 3:4]
            self.bbox_min, self.bbox_max = centers - radii, centers + radii
            self.m_bbox = mi.ScalarBoundingBox3f(self.bbox_min.min(axis=0),
                                                 self.bbox_max.max(axis=0))
            self.area = float(math.pi * np.square(radii).sum())
            self.initialize()

        # Record access

        def _load(self, i, active=True):
            if scalar:
                base = STRIDE * min(int(i), self.n - 1)
                return mi.ArrayXf(self.records[base:base + STRIDE])
            return dr.gather(mi.ArrayXf, self.records, i, active,
                             shape=(STRIDE, self.n))

        def _load_node(self, c, active=True):
            if scalar:
                base = NSTRIDE * min(int(c), self.n_nodes - 1)
                return mi.ArrayXf(self.nodes[base:base + NSTRIDE])
            return dr.gather(mi.ArrayXf, self.nodes, c, active,
                             shape=(NSTRIDE, self.n_nodes))

        def _load_cluster(self, i, active=True):
            '''Record of the i-th cluster node'''
            if scalar:
                node = self.clusters[min(int(i), self.n_clusters - 1)]
            else:
                node = dr.gather(mi.UInt32, self.clusters, i, active)
            return self._load_node(node, active)

        @staticmethod
        def _center(rec):
            return mi.Point3f(rec[0], rec[1], rec[2])

        @staticmethod
        def _falloff(rec, w):
            '''Spot attenuation towards ``w`` (from the light to the receiver)'''
            z = dr.dot(w, mi.Vector3f(rec[8], rec[9], rec[10]))
            return dr.select(rec[7] > 0.5, smoothstep((z - rec[11]) * rec[12]),
                             1.0)

        def emission(self, index, w, active=True):
            '''Radiance of light ``index`` towards the direction ``w``
            (from the light to the receiver)'''
            rec = self._load(index, active)
            return mi.Color3f(rec[4], rec[5], rec[6]) * self._falloff(rec, w)

        # Light selection

        def _weight(self, rec, p):
            '''Unoccluded irradiance that a light produces at ``p``, up to a
            constant: P / (4 pi (d^2 + r^2)) times the spot falloff'''
            v = p - self._center(rec)
            d2 = dr.squared_norm(v)
            w = v * dr.rsqrt(dr.maximum(d2, 1e-20))
            return rec[14] / (d2 + dr.square(rec[3])) * self._falloff(rec, w)

        def _node_weight(self, rec, p):
            '''Summed weight numerator of a node over its squared distance
            (at least half the sphere radius, as in Cycles), times the
            cosine of the smallest angle between the axis of a light in the
            node and the direction to ``p`` that the node's cone allows.
            Zero when no light of the node can reach ``p``.'''
            v = p - self._center(rec)
            d2 = dr.squared_norm(v)
            r2 = dr.square(rec[3])
            inside = d2 <= r2
            # theta_u: half angle under which the sphere is seen from p
            cos_u = dr.select(inside, -1.0,
                              dr.safe_sqrt(1.0 - r2 / dr.maximum(d2, 1e-20)))
            theta_u = dr.acos(cos_u)
            w = v * dr.rsqrt(dr.maximum(d2, 1e-20))
            cos_t = dr.dot(w, mi.Vector3f(rec[5], rec[6], rec[7]))
            theta = dr.acos(dr.clip(cos_t, -1.0, 1.0))
            theta_p = dr.maximum(theta - rec[8] - theta_u, 0.0)
            return dr.select(theta_p < rec[9],
                             rec[4] / dr.maximum(d2, 0.25 * r2)
                             * dr.cos(theta_p), 0.0)

        def _reservoir(self, begin, end, weight, u, active):
            '''Weighted reservoir sampling over the entries ``begin`` to
            ``end``: entry i replaces the choice with probability
            w_i / (w_begin + .. + w_i), and the sample is rescaled to the
            branch taken so that it can be reused. Returns the choice, its
            probability and the sample.'''
            def cond(i, total, k, wk, u):
                return active & (i < end)

            def body(i, total, k, wk, u):
                w = weight(i)
                total = total + w
                # Scalar variants evaluate both branches, so the division
                # must not raise for a zero total
                prob = dr.select(total > 0.0, w / dr.maximum(total, 1e-30),
                                 0.0)
                accept = u < prob
                u = dr.select(accept, u / dr.maximum(prob, 1e-30),
                              (u - prob) / dr.maximum(1.0 - prob, 1e-30))
                return (i + 1, total, dr.select(accept, i, k),
                        dr.select(accept, w, wk), dr.clip(u, 0.0, 1.0))

            i, total, k, wk, u = dr.while_loop(
                (mi.UInt32(begin), mi.Float(0.0), mi.UInt32(begin),
                 mi.Float(0.0), mi.Float(u)),
                cond, body, label='cycles_lights: reservoir')
            return k, dr.select(total > 0.0, wk / dr.maximum(total, 1e-30),
                                0.0), u

        def _weight_total(self, begin, end, weight, active):
            def cond(i, total):
                return active & (i < end)

            def body(i, total):
                return i + 1, total + weight(i)

            return dr.while_loop((mi.UInt32(begin), mi.Float(0.0)), cond,
                                 body, label='cycles_lights: weight sum')[1]

        def _select(self, p, u, active=True):
            '''Choose a light for the shading point ``p`` with the sample
            ``u``. Returns its index, its probability and the sample remapped
            to [0, 1) for reuse.'''
            if self.selection == 'uniform':
                n_f = mi.Float(self.count)
                su = u * n_f
                k = dr.minimum(mi.UInt32(su), self.count - 1)
                return k, dr.rcp(n_f), su - mi.Float(k)

            c, p_c, u = self._reservoir(
                0, self.cluster_count,
                lambda i: self._node_weight(self._load_cluster(i), p),
                u, active)
            cl = self._load_cluster(c, active)
            start = mi.UInt32(cl[12])
            k, p_k, u = self._reservoir(
                start, start + mi.UInt32(cl[13]),
                lambda i: self._weight(self._load(i), p), u, active)
            return k, p_c * p_k, u

        def _pmf(self, k, p, active=True):
            '''Probability that _select() picks light ``k`` at ``p``'''
            if self.selection == 'uniform':
                return dr.rcp(mi.Float(self.count))
            rec = self._load(k, active)
            cl = self._load_node(mi.UInt32(rec[13]), active)
            start = mi.UInt32(cl[12])
            total_c = self._weight_total(
                0, self.cluster_count,
                lambda i: self._node_weight(self._load_cluster(i), p),
                active)
            total_k = self._weight_total(
                start, start + mi.UInt32(cl[13]),
                lambda i: self._weight(self._load(i), p), active)
            pmf = self._node_weight(cl, p) / dr.maximum(total_c, 1e-30) \
                * self._weight(rec, p) / dr.maximum(total_k, 1e-30)
            return dr.select(active & (total_c > 0.0) & (total_k > 0.0),
                             pmf, 0.0)

        # Intersection

        def ray_intersect_preliminary(self, ray, prim_index=0, active=True):
            rec = self._load(prim_index, active)
            c = self._center(rec)
            r2 = dr.square(rec[3])
            # The disk faces the ray origin. Rays that start within the
            # radius miss, see the module docstring.
            v = ray.o - c
            dist2 = dr.squared_norm(v)
            dist = dr.sqrt(dist2)
            cos_d = dr.dot(v, ray.d) / dist
            t = -dist / cos_d
            hit = (dist2 > r2) & (cos_d < 0.0) & (t <= ray.maxt) \
                & (dr.squared_norm(ray(t) - c) < r2) & active

            pi = zeros(mi.PreliminaryIntersection3f)
            pi.t = dr.select(hit, t, dr.inf)
            pi.valid = hit
            pi.prim_index = prim_index
            return pi

        def compute_surface_interaction(self, ray, pi,
                                        ray_flags=mi.RayFlags.Default,
                                        active=True):
            rec = self._load(pi.prim_index, active)
            c = self._center(rec)
            n = dr.normalize(ray.o - c)
            si = dr.zeros(mi.SurfaceInteraction3f)
            si.t = pi.t
            p = ray(pi.t)
            # Re-project onto the disk to improve accuracy
            si.p = p + dr.dot(c - p, n) * n
            si.n = n
            si.sh_frame.n = n
            frame = mi.Frame3f(n)
            si.dp_du = frame.s
            si.dp_dv = frame.t
            # The first UV coordinate carries the light index (see
            # pdf_direction)
            si.uv = mi.Point2f(mi.Float(pi.prim_index), 0.0)
            si.prim_index = pi.prim_index
            si.shape = pi.shape
            return si

        # Sampling

        def sample_direction(self, it, sample, active=True):
            # Choose a light, then a point uniformly on the disk of that
            # light facing the reference point
            k, pmf, sx = self._select(it.p, sample.x, active)
            rec = self._load(k, active)
            c = self._center(rec)
            r = rec[3]

            v = it.p - c
            d = dr.norm(v)
            n = v / dr.maximum(d, 1e-12)
            frame = mi.Frame3f(n)
            xy = mi.warp.square_to_uniform_disk_concentric(
                mi.Point2f(sx, sample.y)) * r
            p = c + frame.s * xy.x + frame.t * xy.y

            ds = zeros(mi.DirectionSample3f)
            ds.p = p
            ds.n = n
            ds.uv = mi.Point2f(mi.Float(k), 0.0)
            ds.time = it.time
            # BSDF-sampled rays cannot reach a light from within its radius
            ds.delta = d <= r
            ds.d = p - it.p
            ds.dist = dr.norm(ds.d)
            ds.d = ds.d / ds.dist
            # The receiver lies at height d over the disk
            cos_l = d / ds.dist
            ds.pdf = dr.select(active & (d > 0.0) & (pmf > 0.0),
                               dr.square(ds.dist) * pmf
                               / (math.pi * dr.square(r) * cos_l), 0.0)
            return ds

        def pdf_direction(self, it, ds, active=True):
            k = mi.UInt32(ds.uv.x)
            rec = self._load(k, active)
            n = dr.normalize(it.p - self._center(rec))
            cos_l = dr.dot(n, -ds.d)
            pdf = dr.square(ds.dist) * self._pmf(k, it.p, active) \
                / (math.pi * dr.square(rec[3]) * cos_l)
            return dr.select(active & (cos_l > 0.0), pdf, 0.0)

        # Miscellaneous

        def bbox(self, prim_index=None):
            if prim_index is None:
                return self.m_bbox
            return mi.ScalarBoundingBox3f(self.bbox_min[prim_index],
                                          self.bbox_max[prim_index])

        def surface_area(self):
            return mi.Float(self.area)

        def primitive_count(self):
            return self.n

        def to_string(self):
            return f'CyclesLights[count={self.n}, nodes={self.n_nodes}, ' \
                f'leaves={self.n_leaves}, clusters={self.n_clusters}, ' \
                f'bbox={self.m_bbox}]'

    class CyclesLightsEmitter(mi.Emitter):
        '''Emitter of the cycles_lights shape: per-light radiance with the
        spot falloff, sampled through the shape'''
        def __init__(self, props):
            mi.Emitter.__init__(self, props)
            self.m_flags = mi.EmitterFlags.Surface

        def eval(self, si, active=True):
            # The direction from the light to the receiver is the one the
            # ray came from
            return self.get_shape().emission(
                si.prim_index, si.to_world(si.wi), active)

        def sample_direction(self, it, sample, active=True):
            shape = self.get_shape()
            ds = shape.sample_direction(it, sample, active)
            active = active & (ds.pdf > 0.0)
            spec = shape.emission(mi.UInt32(ds.uv.x), -ds.d, active)
            ds.emitter = emitter_ptr(self)
            return ds, dr.select(active, spec / ds.pdf, 0.0)

        def pdf_direction(self, it, ds, active=True):
            return self.get_shape().pdf_direction(it, ds, active)

        def eval_direction(self, it, ds, active=True):
            return self.get_shape().emission(mi.UInt32(ds.uv.x), -ds.d, active)

        def sample_wavelengths(self, si, sample, active=True):
            return dr.zeros(mi.Wavelength), mi.Spectrum(1.0)

        def bbox(self):
            return self.get_shape().bbox()

        def to_string(self):
            return 'CyclesLightsEmitter[]'

    mi.register_shape('cycles_lights', lambda props: CyclesLights(props))
    mi.register_emitter('cycles_lights_emitter',
                        lambda props: CyclesLightsEmitter(props))
