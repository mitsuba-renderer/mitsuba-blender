from __future__ import annotations
from typing import TYPE_CHECKING
from enum import Enum
from .common import get_texture

if TYPE_CHECKING:
    import mitsuba as mi
    import drjit as dr



def register(mi, dr):
    class Mix(mi.Texture):
        def __init__(self, props : mi.Properties) -> None:
            super().__init__(props)

            self.blend_type = props.get('blend_type', 'MIX')
            self.clamp_result = props.get('clamp_result', False)
            self.clamp_factor = props.get('clamp_factor', False)
            self.factor = props.get_texture('factor', 0.5)
            self.a = props.get_texture('a')
            self.b = props.get_texture('b')

        def _blend(self, blend_type, a, b, t):
            facm = 1.0 - t

            if blend_type == 'MIX':
                return dr.lerp(a, b, t)
            if blend_type == 'ADD':
                return a + t * b
            if blend_type == 'MULTIPLY':
                return a * (facm + t * b)
            if blend_type == 'SUBTRACT':
                return a - t * b
            if blend_type == 'SCREEN':
                return 1.0 - (facm + t * (1.0 - b)) * (1.0 - a)
            if blend_type == 'DIVIDE':
                return dr.select(dr.neq(b, 0.0), facm * a + t * a / b, a)
            if blend_type == 'DIFFERENCE':
                return facm * a + t * dr.abs(a - b)
            if blend_type == 'DARKEN':
                return dr.lerp(a, dr.minimum(a, b), t)
            if blend_type == 'LIGHTEN':
                return dr.maximum(a, t * b)
            if blend_type == 'OVERLAY':
                lo = a * (facm + 2.0 * t * b)
                hi = 1.0 - (facm + 2.0 * t * (1.0 - b)) * (1.0 - a)
                return dr.select(a < 0.5, lo, hi)
            raise Exception(f'Mix blend type "{blend_type}" is not supported')



        def _process(self, si, val_a, val_b, active):
            fac = self.factor.eval_1(si, active)
            if self.clamp_factor:
                fac = dr.clip(fac, 0.0, 1.0)
            result = self._blend(self.blend_type, val_a, val_b, fac)

            if self.clamp_result:
                return dr.clip(result, 0.0, 1.0)
            return result

        def traverse(self, cb):
            cb.put('a', self.a, mi.ParamFlags.Differentiable)
            cb.put('b', self.b, mi.ParamFlags.Differentiable)


        def eval(self, si, active=True):
            val_a = self.a.eval(si, active)
            val_b = self.b.eval(si, active)
            return mi.UnpolarizedSpectrum(self._process(si, val_a, val_b, active))

        def eval_1(self, si, active=True):
            val_a = self.a.eval_1(si, active)
            val_b = self.b.eval_1(si, active)
            return mi.Float(self._process(si, val_a, val_b, active))

        def eval_3(self, si, active=True):
            val_a = self.a.eval_3(si, active)
            val_b = self.b.eval_3(si, active)

            return mi.Color3f(self._process(si, val_a, val_b, active))


        def mean(self):
            return 0.5

        def resolution(self):
            return self.a.resolution
    mi.register_texture('mix', Mix)



