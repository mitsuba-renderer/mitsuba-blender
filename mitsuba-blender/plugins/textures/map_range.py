from __future__ import annotations # Delayed parsing of type annotations

import drjit as dr
import mitsuba as mi

from .common import get_texture

class MapRange(mi.Texture):
    '''
    Map Range texture.
    '''
    def __init__(self, props):
        mi.Texture.__init__(self, props)
        self.clamp = props.get('clamp', True)
        self.input    = get_texture(props, 'input', 1.0)
        self.from_min = get_texture(props, 'from_min', 0.0)
        self.from_max = get_texture(props, 'from_max', 1.0)
        self.to_min   = get_texture(props, 'to_min', 0.0)
        self.to_max   = get_texture(props, 'to_max', 1.0)
        self.interpolation_type = props.get('interpolation_type', 'LINEAR')
        assert self.interpolation_type == 'LINEAR', self.interpolation_type

    def traverse(self, callback):
        callback.put_object('input',    self.input,    +mi.ParamFlags.Differentiable)
        callback.put_object('from_min', self.from_min, +mi.ParamFlags.Differentiable)
        callback.put_object('from_max', self.from_max, +mi.ParamFlags.Differentiable)
        callback.put_object('to_min',   self.to_min,   +mi.ParamFlags.Differentiable)
        callback.put_object('to_max',   self.to_max,   +mi.ParamFlags.Differentiable)

    def parameters_changed(self, keys):
        pass

    def eval(self, si, active):
        return self.eval_3(si, active)

    def eval_1(self, si, active):
        return self.process(self.input.eval_1(si, active), si, active)

    def eval_3(self, si, active):
        return self.process(self.input.eval_3(si, active), si, active)

    def process(self, value, si, active):
        from_min = self.from_min.eval_1(si, active)
        from_max = self.from_max.eval_1(si, active)
        to_min   = self.to_min.eval_1(si, active)
        to_max   = self.to_max.eval_1(si, active)

        value = (dr.clip(value, from_min, from_max) - from_min) / (from_max - from_min) * (to_max - to_min) + to_min

        if self.clamp:
            value = dr.clip(value, to_min, to_max)

        return value

    def mean(self):
        return self.input.mean() # TODO this is wrong

    def resolution(self):
        return self.input.resolution()

    def spectral_resolution(self):
        pass

    def wavelength_range(self):
        return mi.ScalarVector2f(mi.MI_CIE_MIN, mi.MI_CIE_MAX)

    def is_spatially_varying(self):
        return any([t.is_spatially_varying() for t in [
            self.from_min, self.from_max, self.to_min, self.to_max, self.input
        ]])

    def to_string(self):
        return f'MapRange[input={self.input}]'

mi.register_texture('map_range', MapRange)
