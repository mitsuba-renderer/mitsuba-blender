from __future__ import annotations # Delayed parsing of type annotations

import drjit as dr
import mitsuba as mi

from .common import get_texture

class InvertColor(mi.Texture):
    '''
    Invert color texture.
    '''
    def __init__(self, props):
        mi.Texture.__init__(self, props)
        self.input  = get_texture(props, 'color', 1.0)
        self.fac    = get_texture(props, 'fac', 1.0)

    def traverse(self, callback):
        callback.put_object('color', self.input, +mi.ParamFlags.Differentiable)
        callback.put_object('fac',   self.fac,   +mi.ParamFlags.Differentiable)

    def parameters_changed(self, keys):
        pass

    def eval(self, si, active):
        return self.eval_3(si, active)

    def eval_1(self, si, active):
        return self.process(self.input.eval_1(si, active), si, active)

    def eval_3(self, si, active):
        return self.process(self.input.eval_3(si, active), si, active)

    def process(self, value, si, active):
        f = dr.clip(self.fac.eval_1(si, active), 0.0, 1.0)
        inv_val = 1.0 - value
        return dr.lerp(value, inv_val, f)

    def mean(self):
        raise NotImplementedError

    def resolution(self):
        return self.input.resolution()

    def spectral_resolution(self):
        pass

    def wavelength_range(self):
        return mi.ScalarVector2f(mi.MI_CIE_MIN, mi.MI_CIE_MAX)

    def is_spatially_varying(self):
        return any([t.is_spatially_varying() for t in [
            self.input, self.fac
        ]])

    def to_string(self):
        return f'InvertColor[input={self.input}, fac={self.fac}]'

mi.register_texture('invert', InvertColor)
