
from __future__ import annotations
from typing import TYPE_CHECKING
from enum import Enum
from .common import get_texture

if TYPE_CHECKING:
    import mitsuba as mi
    import drjit as dr


def register(mi, dr):

    class RGBCurve(mi.Texture):
        def _sample(self, table, x, active):
            lut_si = dr.zeros(mi.SurfaceInteraction3f)
            lut_si.uv = mi.Point2f(x, 0.5)
            return table.eval_1(lut_si, active)

        def __init__(self, props: mi.Properties) -> None:
            super().__init__(props)


            self.fac = get_texture(props, 'fac', 1.0)
            self.color = props.get_texture('color')
            self.size = get_texture(props, 'size', 1)

            self.curve_c = props.get_texture('curve_c')
            self.curve_r = props.get_texture('curve_r')
            self.curve_g = props.get_texture('curve_g')
            self.curve_b = props.get_texture('curve_b')



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
            cb.put_object('color', self.color, mi.ParamFlags.Differentiable)
            cb.put_object('fac', self.fac, mi.ParamFlags.Differentiable)
            cb.put_object('curve_c', self.curve_c, mi.ParamFlags.Differentiable)
            cb.put_object('curve_r', self.curve_r, mi.ParamFlags.Differentiable)
            cb.put_object('curve_g', self.curve_g, mi.ParamFlags.Differentiable)
            cb.put_object('curve_b', self.curve_b, mi.ParamFlags.Differentiable)

    
    mi.register_texture('rgb_curve', RGBCurve)
