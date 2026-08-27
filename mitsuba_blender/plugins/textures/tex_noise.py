from __future__ import annotations
from typing import TYPE_CHECKING

from .common import get_texture, get_vector_texture

if TYPE_CHECKING:
    import mitsuba as mi
    import drjit as dr


def register(mi, dr):
    '''Define and register the plugin for the active variant.

    mi.Texture is a different class per variant, so a class defined at
    module scope would bind to whichever variant was active on first
    import and never rebind. Defining it inside this factory means
    register_plugins() can be called again after every set_variant.
    The class body should not be moved out of this function.
    '''

    # Ported from Cycles: intern/cycles/kernel/svm/noise.h (perlin_3d,
    # snoise_3d, noise_fbm) and util/hash.h (hash_uint3). The lattice
    # gradients come from a hash of the integer coordinates, so nothing is
    # stored and the same point always yields the same value.

    def _rot(x, k):
        return (x << k) | (x >> (32 - k))

    def _hash_uint3(kx, ky, kz):
        '''Bob Jenkins' lookup3 finalisation, as Cycles uses it. The
        rotation constants are load bearing: a different mixing function
        gives structurally similar but visibly different noise.'''
        init = 0xdeadbeef + (3 << 2) + 13
        a = mi.UInt32(init) + mi.UInt32(kx)
        b = mi.UInt32(init) + mi.UInt32(ky)
        c = mi.UInt32(init) + mi.UInt32(kz)

        c ^= b; c -= _rot(b, 14)
        a ^= c; a -= _rot(c, 11)
        b ^= a; b -= _rot(a, 25)
        c ^= b; c -= _rot(b, 16)
        a ^= c; a -= _rot(c, 4)
        b ^= a; b -= _rot(a, 14)
        c ^= b; c -= _rot(b, 24)

        return c

    def _fade(t):
        '''6t^5 - 15t^4 + 10t^3: flat at both ends, so the interpolation
        has a continuous slope across cell boundaries.'''
        return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)

    def _floorfrac(x):
        '''Integer and fractional parts. The integer part is reinterpreted
        as unsigned for the hash, matching C's implicit conversion, so
        negative coordinates hash the same way they do in Cycles.'''
        fl = dr.floor(x)
        return mi.UInt32(mi.Int32(fl)), x - fl

    def _grad3(h, x, y, z):
        '''Dot product of (x, y, z) with one of 16 fixed gradients chosen
        by the low bits of the hash.'''
        h = h & 15
        u = dr.select(h < 8, x, y)
        vt = dr.select((h == 12) | (h == 14), x, z)
        v = dr.select(h < 4, y, vt)
        return (dr.select((h & 1) != 0, -u, u) +
                dr.select((h & 2) != 0, -v, v))

    def _tri_mix(v0, v1, v2, v3, v4, v5, v6, v7, x, y, z):
        x1, y1, z1 = 1.0 - x, 1.0 - y, 1.0 - z
        return (z1 * (y1 * (v0 * x1 + v1 * x) + y * (v2 * x1 + v3 * x)) +
                z * (y1 * (v4 * x1 + v5 * x) + y * (v6 * x1 + v7 * x)))

    def _perlin_3d(x, y, z):
        X, fx = _floorfrac(x)
        Y, fy = _floorfrac(y)
        Z, fz = _floorfrac(z)

        u, v, w = _fade(fx), _fade(fy), _fade(fz)
        one = mi.UInt32(1)

        return _tri_mix(
            _grad3(_hash_uint3(X, Y, Z), fx, fy, fz),
            _grad3(_hash_uint3(X + one, Y, Z), fx - 1.0, fy, fz),
            _grad3(_hash_uint3(X, Y + one, Z), fx, fy - 1.0, fz),
            _grad3(_hash_uint3(X + one, Y + one, Z), fx - 1.0, fy - 1.0, fz),
            _grad3(_hash_uint3(X, Y, Z + one), fx, fy, fz - 1.0),
            _grad3(_hash_uint3(X + one, Y, Z + one), fx - 1.0, fy, fz - 1.0),
            _grad3(_hash_uint3(X, Y + one, Z + one), fx, fy - 1.0, fz - 1.0),
            _grad3(_hash_uint3(X + one, Y + one, Z + one),
                   fx - 1.0, fy - 1.0, fz - 1.0),
            u, v, w)

    def _snoise_3d(p):
        '''Signed noise in [-1, 1]. The 0.982 factor is Cycles' empirical
        scale for the 3D case; the modulo repeats the field every 100000
        units to keep the lattice coordinates representable.'''
        correction = 0.5 * dr.select(dr.abs(p) >= 1e6, 1.0, 0.0)
        p = (p - 100000.0 * dr.floor(p * (1.0 / 100000.0))) + correction
        return 0.982 * _perlin_3d(p.x, p.y, p.z)

    def _noise_fbm_3d(p, detail, roughness, lacunarity, normalize):
        '''Sum of octaves at increasing frequency and falling amplitude.

        detail, roughness and lacunarity are Python floats: the octave
        count sets the loop bound at trace time, so they cannot be driven
        by a texture. The converter resolves them to constants.
        '''
        fscale, amp = 1.0, 1.0
        maxamp = 0.0
        total = dr.zeros(mi.Float)

        for _ in range(int(detail) + 1):
            total = total + _snoise_3d(p * fscale) * amp
            maxamp += amp
            amp *= roughness
            fscale *= lacunarity

        rmd = detail - int(detail)
        if rmd != 0.0:
            total2 = total + _snoise_3d(p * fscale) * amp
            if normalize:
                return dr.lerp(0.5 * total / maxamp + 0.5,
                               0.5 * total2 / (maxamp + amp) + 0.5, rmd)
            return dr.lerp(total, total2, rmd)

        return 0.5 * total / maxamp + 0.5 if normalize else total

    class TexNoise(mi.Texture):
        '''Blender's Noise Texture node, 3D fractal Brownian motion.

        Follows Cycles' noise.h. Two divergences from Blender:

        The coordinate. With the Vector input unconnected Blender uses the
        generated texture coordinate, which is object space normalised to
        the bounding box. A Mitsuba texture has the world position and the
        UVs, so the converter passes the world position and the pattern is
        anchored differently: it does not travel with the object and does
        not match a Cycles render of the same scene.

        Only the Fac output and the FBM fractal type are implemented, and
        Distortion is ignored.
        '''

        def __init__(self, props: mi.Properties) -> None:
            super().__init__(props)

            self.vector = get_vector_texture(props, 'vector') if 'vector' in props else None
            self.scale = get_texture(props, 'scale', 5.0)

            self.detail = float(props.get('detail', 2.0))
            self.roughness = float(props.get('roughness', 0.5))
            self.lacunarity = float(props.get('lacunarity', 2.0))
            self.normalize = bool(props.get('normalize', True))

        def eval(self, si, active=True):
            return mi.UnpolarizedSpectrum(self.eval_1(si, active))

        def eval_1(self, si, active=True):
            p = si.p if self.vector is None else self.vector.eval_3(si, active)
            p = p * self.scale.eval_1(si, active)
            return _noise_fbm_3d(p, self.detail, self.roughness,
                                 self.lacunarity, self.normalize)

        def eval_3(self, si, active=True):
            v = self.eval_1(si, active)
            return mi.Color3f(v, v, v)

        def mean(self):
            return 0.5 if self.normalize else 0.0

        def traverse(self, cb):
            # 'vector' is optional: with the input unconnected it is None,
            # which is not a traversable value.
            if self.vector is not None:
                cb.put('vector', self.vector, mi.ParamFlags.Differentiable)
            cb.put('scale', self.scale, mi.ParamFlags.Differentiable)

        def parameters_changed(self, keys=None):
            pass

        def is_spatially_varying(self):
            return True

        def to_string(self):
            return (f'TexNoise[detail={self.detail}, '
                    f'roughness={self.roughness}, '
                    f'lacunarity={self.lacunarity}, '
                    f'normalize={self.normalize},\n'
                    f'  vector = {self.vector},\n'
                    f'  scale = {self.scale}\n]')

    mi.register_texture('tex_noise', TexNoise)
