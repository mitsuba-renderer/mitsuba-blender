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

    class Mix(mi.Texture):
        '''Blender's Mix node

        ShaderNodeMix declares sockets for every data type at once and
        hides the irrelevant ones, so the conveter matches on socket
        identifier rather than display name. Blend mode apply only to
        RGBA: a FLOAT mix is a plein lerp, and the conveter emits 'MIX'
        for it.
        '''

        def __init__(self, props : mi.Properties) -> None:
            super().__init__(props)

            self.blend_type = props.get('blend_type', 'MIX')
            self.clamp_result = props.get('clamp_result', False)
            self.clamp_factor = props.get('clamp_factor', False)
            self.factor = get_texture(props, 'factor', 0.5)
            self.a = get_texture(props, 'a', 1.0)
            self.b = get_texture(props, 'b', 1.0)

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
                return dr.select(b != 0.0, facm * a + t * a / dr.select(b != 0.0, b, 1.0), a)
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

        def traverse(self, cb):
            cb.put('a', self.a, mi.ParamFlags.Differentiable)
            cb.put('b', self.b, mi.ParamFlags.Differentiable)

        def resolution(self):
            return self.a.resolution

        def eval_1_grad(self, si, active=True):
            a = self.a.eval_1(si, active)
            b = self.b.eval_1(si, active)
            t = self.factor.eval_1(si, active)

            # Spatial gradients (du, dv)
            grad_a = self.a.eval_1_grad(si, active)
            grad_b = self.b.eval_1_grad(si, active)
            grad_t = self.factor.eval_1_grad(si, active)

            # Handle clamp_factor
            if self.clamp_factor:
                raw_t = t
                t = dr.clip(raw_t, 0.0, 1.0)

                # d clip(t)/dt
                t_mask = (raw_t > 0.0) & (raw_t < 1.0)
                grad_t = dr.select(t_mask, grad_t, mi.Vector2f(0.0))

            da, db, dt = self._blend_grad(
                self.blend_type, a, b, t
            )

            # Chain rule
            grad = da * grad_a + db * grad_b + dt * grad_t

            # Handle clamp_result
            if self.clamp_result:
                result = self._blend(self.blend_type, a, b, t)

                # d clip(result)/d result
                result_mask = (result > 0.0) & (result < 1.0)
                grad = dr.select(
                    result_mask,
                    grad,
                    mi.Vector2f(0.0)
                )

            return mi.Vector2f(grad)


        def _blend_grad(self, blend_type, a, b, t):
            facm = 1.0 - t

            if blend_type == 'MIX':
                # r = (1-t)a + tb
                da = facm
                db = t
                dt = b - a

            elif blend_type == 'ADD':
                # r = a + tb
                da = 1.0
                db = t
                dt = b

            elif blend_type == 'MULTIPLY':
                # r = a(1-t+tb)
                da = facm + t * b
                db = t * a
                dt = a * (b - 1.0)

            elif blend_type == 'SUBTRACT':
                # r = a - tb
                da = 1.0
                db = -t
                dt = -b

            elif blend_type == 'SCREEN':
                # r = 1 - (1-tb)(1-a)
                da = 1.0 - t * b
                db = t * (1.0 - a)
                dt = b * (1.0 - a)

            elif blend_type == 'DIVIDE':
                # r = a(1-t) + t*a/b, with r=a when b=0
                valid = b != 0.0
                bsafe = dr.select(valid, b, 1.0)

                da_valid = facm + t / bsafe
                db_valid = -t * a / (bsafe * bsafe)
                dt_valid = a / bsafe - a

                da = dr.select(valid, da_valid, 1.0)
                db = dr.select(valid, db_valid, 0.0)
                dt = dr.select(valid, dt_valid, 0.0)

            elif blend_type == 'DIFFERENCE':
                # r = (1-t)a + t|a-b|
                s = dr.sign(a - b)

                da = facm + t * s
                db = -t * s
                dt = dr.abs(a - b)

            elif blend_type == 'DARKEN':
                # r = lerp(a, min(a,b), t)
                m = dr.minimum(a, b)

                da_min = dr.select(a <= b, 1.0, 0.0)
                db_min = dr.select(b < a, 1.0, 0.0)

                da = facm + t * da_min
                db = t * db_min
                dt = m - a

            elif blend_type == 'LIGHTEN':
                # r = max(a, tb)
                x = t * b
                use_x = x > a

                da = dr.select(use_x, 0.0, 1.0)
                db = dr.select(use_x, t, 0.0)
                dt = dr.select(use_x, b, 0.0)

            elif blend_type == 'OVERLAY':
                # lo = a * (1-t + 2tb)
                # hi = 1 - (1-t + 2t(1-b)) * (1-a)

                lo_da = facm + 2.0 * t * b
                lo_db = 2.0 * t * a
                lo_dt = a * (2.0 * b - 1.0)

                hi_da = facm + 2.0 * t * (1.0 - b)
                hi_db = 2.0 * t * (1.0 - a)
                hi_dt = (1.0 - 2.0 * b) * (1.0 - a)

                use_lo = a < 0.5

                da = dr.select(use_lo, lo_da, hi_da)
                db = dr.select(use_lo, lo_db, hi_db)
                dt = dr.select(use_lo, lo_dt, hi_dt)

            else:
                raise Exception(
                    f'Mix blend type "{blend_type}" is not supported'
                )

            return da, db, dt
    mi.register_texture('mix', Mix)



