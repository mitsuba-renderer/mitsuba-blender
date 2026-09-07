'''Blender's Filmic view transform as a Mitsuba post-processing stage.

Filmic is a tone mapping operator by Troy Sobotka that Blender shipped as its
default view transform from 2.79 to 3.6. It maps scene-linear radiance to a
display image the way photographic film would: a smooth sigmoid compresses
about 16.5 stops of dynamic range around middle grey into the display range,
and very bright colors desaturate towards white instead of clipping per
channel. Blender defines the transform through lookup tables; this plugin is
an analytic version reverse-engineered from those tables, together with
Blender's view-level curves, exposure and gamma controls.
'''

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import mitsuba as mi
    import drjit as dr


VIEW_TRANSFORMS = ('Filmic', 'Standard')

# Blender stores its Filmic view transform as lookup tables in the
# OpenColorIO configuration under datafiles/colormanagement: a 65^3 3D LUT
# (desat65cube, shipped as a 33^3 subsample since Blender 4.0) that
# desaturates bright colors, followed by one 4096-entry 1D LUT per contrast
# look. Troy Sobotka authored the tables in 2016 without publishing the code
# that generated them. This plugin evaluates closed-form expressions instead
# of the tables. The constants below were obtained as follows.

# Read from the configuration: middle grey, and the log2 range of the curve
# input in stops around grey. The 3D LUT input covers -10 to +15 stops.
FILMIC_GREY = 0.18
FILMIC_STOPS = (-10.0, 6.5)

# The 3D LUT blends each color towards its largest component M with the
# weight w = ((M - M0) / (M1 - M0))^p, where M1 is the top of the LUT
# domain, 15 stops above grey. A least-squares fit of M0 and p to the 65^3
# table along a pure red ramp gives M0 = 0.18 * 2^6.00 and p = 1.09999
# with an absolute error in w below 2e-6, so these two values are
# presumably the parameters of the original generator.
FILMIC_DESATURATION_STOPS = (6.0, 15.0)
FILMIC_DESATURATION_POWER = 1.1

# The contrast of a look is the first number in the file name of its table
# (filmic_to_0-70_1-03.spi1d for the base view). The second number is not
# used.
FILMIC_BASE_CONTRAST = 0.7

# Each 1D table maps the log exposure d = ln(v / 0.18), clamped to
# [-10 ln 2, 6.5 ln 2], to a display value y. It is approximated by two
# pieces of the generalized logistic
#
#     R(d; m, q) = (1 + (2^q - 1) exp(-m q d))^(-1/q),
#
# a power law v^m in the toe that saturates at 1 with knee sharpness q and
# passes through R(0) = 1/2. Each piece is rescaled to end at 0 or 1:
#
#     y = 1/2 + (R(d; m_t, q_t) - 1/2) / (2 |R(-10 ln 2; m_t, q_t) - 1/2|)   d < 0
#     y = 1/2 + (R(d; m_s, q_s) - 1/2) / (2 |R(6.5 ln 2; m_s, q_s) - 1/2|)   d >= 0
#
# With t = 1.2 / c - 1 for contrast c, the four parameters are
#
#     m_t = c (1 + a_1 t + a_2 t^2 + a_3 t^3),   q_t = 1 + b_1 t + b_2 t^2 + b_3 t^3,
#     m_s = c (1 + e_1 t + e_2 t^2 + e_3 t^3),   q_s = 1 + f_1 t + f_2 t^2 + f_3 t^3,
#
# where (a_i), (b_i), (e_i), (f_i) are the four tuples below. They were fit
# jointly to the seven tables by least squares and then refined with an
# L^6 loss to even out the maximum error across the looks. The maximum
# absolute error per curve is 0.5 to 0.9 of an 8-bit code.
FILMIC_TOE_EXPONENT = (-0.04260, -0.01208, 0.00819)
FILMIC_TOE_SHARPNESS = (0.23524, 0.04299, 0.01407)
FILMIC_SHOULDER_EXPONENT = (-0.60998, 0.31700, -0.04726)
FILMIC_SHOULDER_SHARPNESS = (1.04157, 0.33046, -0.16397)


def filmic_curve(contrast):
    '''The (exponent, sharpness) pairs of the toe and of the shoulder of
    the Filmic curve with the given contrast. The exponents relative to
    the contrast and the sharpness values are cubic polynomials in ``t``
    with a constant term of 1.'''
    t = 1.2 / contrast - 1.0
    poly = lambda coeffs: 1.0 + sum(c * t ** (i + 1) for i, c in enumerate(coeffs))
    return ((contrast * poly(FILMIC_TOE_EXPONENT), poly(FILMIC_TOE_SHARPNESS)),
            (contrast * poly(FILMIC_SHOULDER_EXPONENT), poly(FILMIC_SHOULDER_SHARPNESS)))


def register(mi, dr):
    '''
    Define and register the plugin for the active variant

    mi.PostProcess is a different class per variant, so the class is
    defined inside this factory and re-created after every set_variant,
    like the other plugins of this package.
    '''
    Color3f, TensorXf = mi.Color3f, mi.TensorXf

    class Filmic(mi.PostProcess):
        ''' Post-processing stage applying Blender's display pipeline

        Nested in a film, this stage transforms the developed image the way
        Blender's view settings would: the view-level RGB curves, the
        exposure scale, the Filmic view transform with its contrast look
        (or the plain sRGB transfer function for the Standard view) and the
        display gamma. Blender's pipeline ends with sRGB-encoded display
        values; this stage decodes them again and returns display-linear
        values, which the film encodes when it writes 8-bit images. The
        pixel pipeline is traced with Dr.Jit and requires a JIT variant.

        The Filmic view emulates photographic film in two steps. It first
        blends colors whose largest component ``M`` lies more than 6 stops
        above middle grey towards ``M``, which bleaches bright saturated
        colors and reaches white at 15 stops. Each channel then passes
        through a sigmoid of the log exposure that maps 10 stops below
        middle grey to 0, middle grey to 0.5 and 6.5 stops above it to 1,
        with a toe and shoulder shape set by ``contrast``. Blender
        implements both steps with lookup tables. This plugin uses the
        closed-form expressions given with the module constants.

        Parameters: ``view_transform`` ("Filmic" or "Standard"),
        ``exposure`` (stops), ``gamma`` and ``contrast`` (Filmic view
        only). Blender's contrast looks range from 0.35 ("Very Low
        Contrast") to 1.2 ("Very High Contrast") around the default of
        0.7. ``view_curves`` names a float32 EXR image resolved like a
        texture path. It holds a 3-channel row with the per-channel view
        curves over the domain given by its ``domain_min`` and
        ``domain_max`` metadata, and the curves are extrapolated linearly
        outside it.
        '''

        def __init__(self, props: mi.Properties) -> None:
            super().__init__(props)
            if not dr.is_jit_v(mi.Float):
                raise RuntimeError(f'The filmic plugin requires a JIT variant, not {mi.variant()}')
            self.view_transform = str(props.get('view_transform', 'Filmic'))
            self.exposure = float(props.get('exposure', 0.0))
            self.gamma = float(props.get('gamma', 1.0))
            self.contrast = float(props.get('contrast', FILMIC_BASE_CONTRAST))
            self.view_curves_file = str(props.get('view_curves', ''))
            if self.view_transform not in VIEW_TRANSFORMS:
                raise ValueError(f'Unsupported view transform "{self.view_transform}", '
                                 f'expected one of {VIEW_TRANSFORMS}')
            if self.gamma <= 0.0:
                raise ValueError('The gamma must be positive')
            if self.contrast <= 0.0:
                raise ValueError('The contrast must be positive')

            self.view_curves = None
            if self.view_curves_file:
                bitmap = mi.Bitmap(str(mi.file_resolver().resolve(self.view_curves_file)))
                if bitmap.channel_count() != 3:
                    raise ValueError(f'{self.view_curves_file}: expected an RGB image')
                table = np.array(bitmap, dtype=np.float32).reshape(-1, 3)
                self.view_curves = mi.Texture1f(TensorXf(table), filter_mode=dr.FilterMode.Linear,
                                                wrap_mode=dr.WrapMode.Clamp)
                lo, hi = (bitmap.metadata().get('domain_min', 0.0),
                          bitmap.metadata().get('domain_max', 1.0))
                # Domain of the table and the slopes of its end segments
                # for the linear extrapolation
                dx = (hi - lo) / (table.shape[0] - 1)
                self.curves_domain = (lo, hi)
                self.curves_slopes = (Color3f((table[1] - table[0]) / dx),
                                      Color3f((table[-1] - table[-2]) / dx))

        # Pixel pipeline

        def _view_curves(self, x):
            '''Per-channel table lookup, extrapolated linearly outside of
            the table's domain.'''
            lo, hi = self.curves_domain
            n = self.view_curves.shape[0]
            u = (x - lo) / (hi - lo)
            # Sample i lies at the center of texel i
            pos = (u * (n - 1) + 0.5) / n
            y = Color3f(*[self.view_curves.eval(mi.Point1f(pos[c]))[c] for c in range(3)])
            below, above = self.curves_slopes
            return y + dr.minimum(u, 0.0) * (hi - lo) * below \
                     + dr.maximum(u - 1.0, 0.0) * (hi - lo) * above

        def _filmic(self, rgb):
            '''Blender's Filmic view: sRGB-encoded display values of a
            scene-linear color.'''
            rgb = dr.select(rgb > 1e-10, rgb, 1e-10)

            # Desaturation
            peak = dr.max(rgb)
            lo, hi = (FILMIC_GREY * 2.0 ** s for s in FILMIC_DESATURATION_STOPS)
            weight = dr.clip((peak - lo) / (hi - lo), 0.0, 1.0) ** FILMIC_DESATURATION_POWER
            rgb = dr.lerp(rgb, peak, weight)

            # Contrast curve
            lo, hi = (s * math.log(2.0) for s in FILMIC_STOPS)
            d = dr.clip(dr.log(rgb / FILMIC_GREY), lo, hi)

            def piece(m, q, end):
                '''Constants of (1 + k exp(-a d))^e and the distance of this
                logistic from 0.5 at the end of the piece.'''
                a, k, e = m * q, 2.0 ** q - 1.0, -1.0 / q
                return a, k, e, abs((1.0 + k * math.exp(-a * end)) ** e - 0.5)

            toe, shoulder = filmic_curve(self.contrast)
            a, k, e, extent = (dr.select(d < 0.0, t, s) for t, s in
                               zip(piece(*toe, lo), piece(*shoulder, hi)))
            return 0.5 + 0.5 * ((1.0 + k * dr.exp(-a * d)) ** e - 0.5) / extent

        @staticmethod
        def _srgb_encode(x):
            return dr.select(x <= 0.0031308, 12.92 * x, 1.055 * x ** (1.0 / 2.4) - 0.055)

        @staticmethod
        def _srgb_decode(x):
            return dr.select(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)

        def _apply(self, rgb):
            '''The pipeline on a Color3f of scene-linear values, returning
            display-linear values.'''
            if self.view_curves is not None:
                rgb = self._view_curves(rgb)
            rgb = dr.select(dr.isnan(rgb), 0.0, rgb) * 2.0 ** self.exposure
            if self.view_transform == 'Standard' and self.gamma == 1.0:
                return dr.clip(rgb, 0.0, 1.0)
            if self.view_transform == 'Filmic':
                display = self._filmic(rgb)
            else:
                display = self._srgb_encode(dr.clip(rgb, 0.0, 1.0))
            display = dr.clip(display, 0.0, 1.0)
            if self.gamma != 1.0:
                display = display ** (1.0 / self.gamma)
            return self._srgb_decode(display)

        # Public interface

        def eval(self, image, channels=()):
            '''Apply the pipeline to the leading R, G, B channels of a
            (height, width, channels) tensor. The other channels pass
            through. A single kernel gathers each pixel, transforms it and
            scatters it to a new tensor.'''
            image = TensorXf(image)
            h, w, c = image.shape
            if c < 3 or list(channels[:3]) not in ([], ['R', 'G', 'B']):
                raise ValueError('The filmic plugin expects an image with leading R, G, B channels')
            base = dr.arange(mi.UInt32, h * w) * c
            values = [dr.gather(mi.Float, image.array, base + i) for i in range(c)]
            values[:3] = self._apply(Color3f(*values[:3]))
            result = TensorXf(mi.ArrayXf(values), flip_axes=True)
            return dr.reshape(TensorXf, result, (h, w, c))

        def to_string(self):
            return (f'Filmic[view_transform={self.view_transform}, contrast={self.contrast}, '
                    f'exposure={self.exposure}, gamma={self.gamma}, '
                    f'view_curves={self.view_curves_file!r}]')

    mi.register_postprocess('filmic', Filmic)
