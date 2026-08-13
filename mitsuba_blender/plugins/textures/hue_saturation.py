from __future__ import annotations # Delayed parsing of type annotations

import drjit as dr
import mitsuba as mi

from .common import get_texture, hsv2rgb, rgb2hsv

def register(mi, dr):
    class HueSaturationValue(mi.Texture):
        '''
        Hue-Saturation-Value texture.
        '''
        def __init__(self, props):
            mi.Texture.__init__(self, props)
            self.hue        = get_texture(props, 'hue', 0.5)
            self.saturation = get_texture(props, 'saturation', 1.0)
            self.value      = get_texture(props, 'value', 1.0)
            self.mix        = get_texture(props, 'mix', 1.0)
            self.input      = get_texture(props, 'input', 1.0)


        def eval(self, si, active):
            return self.eval_3(si, active)

        def eval_1(self, si, active):
            return self.input.eval_1(si, active) * self.value.eval_1(si, active)

        def eval_3(self, si, active):
            hue        = self.hue.eval_1(si, active)
            saturation = self.saturation.eval_1(si, active)
            value      = self.value.eval_1(si, active)
            mix        = self.mix.eval_1(si, active)
            color      = self.input.eval_3(si, active)

            hsv = rgb2hsv(color)
            hsv.x += 360.0 * (hue - 0.5)
            hsv.y *= saturation
            hsv.z *= value

            return dr.lerp(color,  hsv2rgb(hsv) , mix)

        def mean(self):
            return 0.5

        def traverse(self, callback):
            callback.put_object('hue',        self.hue,        +mi.ParamFlags.Differentiable)
            callback.put_object('saturation', self.saturation, +mi.ParamFlags.Differentiable)
            callback.put_object('value',      self.value,      +mi.ParamFlags.Differentiable)
            callback.put_object('mix',        self.mix,        +mi.ParamFlags.Differentiable)
            callback.put_object('input',      self.input,      +mi.ParamFlags.Differentiable)


    mi.register_texture('hue_saturation_value', HueSaturationValue)
