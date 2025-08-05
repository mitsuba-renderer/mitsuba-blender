from __future__ import annotations # Delayed parsing of type annotations

import drjit as dr
import mitsuba as mi

from .common import get_texture

class Clamp(mi.Texture):
    '''
    Map Range texture.
    '''
    def __init__(self, props):
        mi.Texture.__init__(self, props)
        self.input = get_texture(props, 'input', 1.0)
        self.min = get_texture(props, 'min', 0.0)
        self.max = get_texture(props, 'max', 1.0)
        self.clamp_type = props.get('clamp_type', 'RANGE')

    def traverse(self, callback):
        callback.put_object('input', self.input, +mi.ParamFlags.Differentiable)
        callback.put_object('min', self.min, +mi.ParamFlags.Differentiable)
        callback.put_object('max', self.max, +mi.ParamFlags.Differentiable)

    def parameters_changed(self, keys):
        pass

    def eval(self, si, active):
        return self.eval_3(si, active)

    def eval_1(self, si, active):
        return self.process(self.input.eval_1(si, active), si, active)

    def eval_3(self, si, active):
        return self.process(self.input.eval_3(si, active), si, active)

    def process(self, value, si, active):
        min_value = self.min.eval_1(si, active)
        max_value = self.max.eval_1(si, active)

        if self.clamp_type == 'RANGE':
            min_value, max_value = dr.minimum(min_value, max_value), dr.maximum(min_value, max_value)
            return dr.clip(value, min_value, max_value)
        else:
            return dr.minimum(dr.maximum(value, min_value), max_value)

    def mean(self):
        return self.input.mean() # TODO this is wrong

    def resolution(self):
        return mi.ScalarVector2i(1, 1)

    def spectral_resolution(self):
        pass

    def wavelength_range(self):
        return mi.ScalarVector2f(mi.MI_CIE_MIN, mi.MI_CIE_MAX)

    def is_spatially_varying(self):
        return any([t.is_spatially_varying() for t in [self.input, self.min, self.max]])

    def to_string(self):
        return f'Clamp[input={self.input}]'

mi.register_texture('clamp', Clamp)
