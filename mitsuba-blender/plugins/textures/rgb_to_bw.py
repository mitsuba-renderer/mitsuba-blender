from __future__ import annotations # Delayed parsing of type annotations

import drjit as dr
import mitsuba as mi

from .common import get_texture

class RGB2BW(mi.Texture):
    '''
    RGB to BW texture.
    '''
    def __init__(self, props):
        mi.Texture.__init__(self, props)
        self.color = get_texture(props, 'color', 0.5)

    def traverse(self, callback):
        callback.put_object('color', self.color, +mi.ParamFlags.Differentiable)

    def parameters_changed(self, keys):
        pass

    def eval(self, si, active):
        return self.eval_3(si, active)

    def eval_1(self, si, active):
        return mi.Float(mi.luminance(self.color.eval_3(si, active)))

    def eval_3(self, si, active):
        return mi.Color3f(mi.luminance(self.color.eval_3(si, active)))

    def mean(self):
        return mi.luminance(self.color.mean()) # TODO this is wrong

    def resolution(self):
        return self.color.resolution()

    def spectral_resolution(self):
        return self.color.spectral_resolution()

    def wavelength_range(self):
        return self.color.wavelength_range()

    def is_spatially_varying(self):
        return self.color.is_spatially_varying()

    def to_string(self):
        return f'RGB2BW[color={self.color}]'

mi.register_texture('rgb_to_bw', RGB2BW)
