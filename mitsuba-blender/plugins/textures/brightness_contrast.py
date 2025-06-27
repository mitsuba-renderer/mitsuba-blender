from __future__ import annotations # Delayed parsing of type annotations

import drjit as dr
import mitsuba as mi

from .common import get_texture

class BrightnessContrast(mi.Texture):
    '''
    Brightness and Contrast shader node
    '''
    def __init__(self, props):
        mi.Texture.__init__(self, props)
        self.input          = get_texture(props, 'color', 1.0)
        self.brightness     = get_texture(props, 'brightness', 0.0)
        self.contrast       = get_texture(props, 'contrast', 0.0)

    def traverse(self, callback):
        callback.put_object('input',        self.input,         +mi.ParamFlags.Differentiable)
        callback.put_object('brightness',   self.brightness,    +mi.ParamFlags.Differentiable)
        callback.put_object('contrast',     self.contrast,      +mi.ParamFlags.Differentiable)

    def parameters_changed(self, keys):
        pass

    def eval(self, si, active):
        return self.eval_3(si, active)

    def eval_1(self, si, active):
        return self.process(self.input.eval_1(si, active), si, active)

    def eval_3(self, si, active):
        return self.process(self.input.eval_3(si, active), si, active)

    def process(self, value, si, active):
        bright = self.brightness.eval_1(si, active)
        cont   = self.contrast.eval_1(si, active)

        # From OSL implementation of Blender shader node
        a = 1.0 + cont
        b = bright - cont * 0.5
        return dr.maximum(a * value + b, 0.0)

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
            self.brightness, self.contrast
        ]])

    def to_string(self):
        return f'''BrightnessContrast[
            color={self.input},
            brightness={self.brightness},
            contrast={self.contrast}]'''

mi.register_texture('brightness_contrast', BrightnessContrast)