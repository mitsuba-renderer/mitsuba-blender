from __future__ import annotations

from typing import TYPE_CHECKING

import drjit as dr
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

    class MapRange(mi.Texture):
        ''' Blender's Map Range node.

        Follows node_shader_map_range.cc: the input is not clamped to the
        from-range, the smoothstep variants clamp the factor to [0, 1]
        regardless of the clamp setting, and clamp applies to the result only.
        Float and vector modes differ only in which eval wiedth the caller uses.
        '''
        def __init__(self, props: mi.Properties):
            super().__init__(props)
            self.clamp = props.get('clamp', True)
            self.vector = props.get('vector', True)


            self.steps = get_texture(props, 'steps', 4.0)
            self.input = get_texture(props, 'input', 1.0)
            self.from_min = get_texture(props, 'from_min', 0.0)
            self.from_max = get_texture(props, 'from_max', 1.0)
            self.to_min = get_texture(props, 'to_min', 0.0)
            self.to_max = get_texture(props, 'to_max', 1.0)
            self.interpolation_type = props.get('interpolation_type', 'LINEAR')


        def _safe_divide(self, a, b):
            return dr.select(b != 0.0, a / dr.select(b != 0.0, b, 1.0), 0.0)

        def _clamp_range(self, value, lo, hi):
            return dr.select(hi > lo,
                             dr.clip(value, lo, hi),
                             dr.clip(value, hi, lo))

        def process(self, si, active):
            ev = (lambda t: t.eval_3(si, active)) if self.vector else (lambda t: t.eval_1(si, active))
            v = ev(self.input)
            from_min, from_max = ev(self.from_min), ev(self.from_max)
            to_min, to_max = ev(self.to_min), ev(self.to_max)

            factor = self._safe_divide(v - from_min, from_max - from_min)

            if self.interpolation_type == 'STEPPED':
                steps = ev(self.steps)
                factor = self._safe_divide(dr.floor(factor * (steps + 1.0)), steps)
            elif self.interpolation_type == 'SMOOTHSTEP':
                factor = dr.clip(factor, 0.0, 1.0)
                factor = (3.0 - 2.0 * factor) * factor * factor
            elif self.interpolation_type == 'SMOOTHERSTEP':
                factor = dr.clip(factor, 0.0, 1.0)
                factor = factor * factor * factor * (factor * (factor * 6.0 - 15.0) + 10.0)

            v = to_min + factor * (to_max - to_min)

            if self.clamp:
                v = self._clamp_range(v, to_min, to_max)
            return v


        def eval(self, si: mi.SurfaceInteraction3f, active=True):
            mi.UnpolarizedSpectrum(self.eval_3(si, active))

        def eval_1(self, si, active=True):
            return mi.Float(self.process(si, active))

        def eval_3(self, si, active=True):
            return mi.Color3f(self.process(si, active))

        def mean(self):
            return 0.5


        def traverse(self, cb):
            cb.put('input', self.input, mi.ParamFlags.Differentiable)
            cb.put('from_min', self.from_min, mi.ParamFlags.Differentiable)
            cb.put('from_max', self.from_max, mi.ParamFlags.Differentiable)
            cb.put('to_min', self.to_min, mi.ParamFlags.Differentiable)
            cb.put('to_max', self.to_max, mi.ParamFlags.Differentiable)


        def is_spatially_varying(self):
            return any([t.is_spatially_varying() for t in [
                self.from_min, self.from_max, self.to_min, self.to_max, self.input
            ]])

        def resolution(self):
            return self.input.resolution()
    mi.register_texture('map_range', MapRange)


