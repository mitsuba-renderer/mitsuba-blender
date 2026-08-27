from __future__ import annotations

from typing import TYPE_CHECKING

from enum import Enum
from .common import get_texture

if TYPE_CHECKING:
    import mitsuba as mi
    import drjit as dr


def register(mi, dr):
    '''
    Define and register the plugin for the active variant

    mi.Texture is a different class per variant, so a class defined at
    module scope would bind to whichever variant was active on first
    import and never rebind. Defining it inside this factory means
    register_plugins() can be called again after every set_variant.
    The class body should not be moved out of this function.
    '''


    class RGBCurve(mi.Texture):
        ''' Blender's RGB Curve node.

        The combined curve is applied first, then per channel curve.
        Each curve arrives as a 2xN bitmap sampled with wrap_map clamp,
        since Properties cannot hold a float array.
        '''
        def _sample(self, table, x, active):
            lut_si = dr.zeros(mi.SurfaceInteraction3f)
            lut_si.uv = mi.Point2f(x, 0.5)
            return table.eval_1(lut_si, active)

        def __init__(self, props: mi.Properties) -> None:
            super().__init__(props)


            self.fac = get_texture(props, 'fac', 1.0)
            self.color = get_texture(props, 'color')

            self.curve_c = get_texture(props, 'curve_c')
            self.curve_r = get_texture(props, 'curve_r')
            self.curve_g = get_texture(props, 'curve_g')
            self.curve_b = get_texture(props, 'curve_b')



        def eval(self, si, active):
            return mi.UnpolarizedSpectrum(self.eval_3(si, active))

        def eval_1(self, si, active):
            return mi.luminance(self.eval_3(si, active))

        def eval_1_grad(self, si, active=True):
            return mi.Vector2f(0.0)

        def eval_3(self, si, active):
            rgb = self.color.eval_3(si, active)
            fac = self.fac.eval_1(si, active)

            r = self._sample(self.curve_r, self._sample(self.curve_c, rgb.x, active), active)
            g = self._sample(self.curve_g, self._sample(self.curve_c, rgb.y, active), active)
            b = self._sample(self.curve_b, self._sample(self.curve_c, rgb.z, active), active)

            return dr.lerp(rgb, mi.Color3f(r, g, b), fac)

        def mean(self):
            return 0.5

        def traverse(self, cb):
            cb.put('color', self.color, mi.ParamFlags.Differentiable)
            cb.put('fac', self.fac, mi.ParamFlags.Differentiable)
            cb.put('curve_c', self.curve_c, mi.ParamFlags.NonDifferentiable)
            cb.put('curve_r', self.curve_r, mi.ParamFlags.NonDifferentiable)
            cb.put('curve_g', self.curve_g, mi.ParamFlags.NonDifferentiable)
            cb.put('curve_b', self.curve_b, mi.ParamFlags.NonDifferentiable)

        def parameters_changed(self, keys=None):
            pass

        def is_spatially_varying(self):
            return (self.color.is_spatially_varying() or
                    self.fac.is_spatially_varying() or
                    self.curve_c.is_spatially_varying() or
                    self.curve_r.is_spatially_varying() or
                    self.curve_g.is_spatially_varying() or
                    self.curve_r.is_spatially_varying())

        def to_string(self):
            return (f'RGBCurve[\n color = {self.color}, \n fac = {self.fac}\n]')


    mi.register_texture('rgb_curve', RGBCurve)






