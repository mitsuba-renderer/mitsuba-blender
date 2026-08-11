from __future__ import annotations # Delayed parsing of type annotations

import drjit as dr
import mitsuba as mi

from .common import get_texture

def modulo(a, b):
    return (a - mi.Int32(a)) + mi.Int32(a) % b

def rgb2hsv(rgb):
    max_rgb = dr.max(rgb)
    min_rgb = dr.min(rgb)
    delta = max_rgb - min_rgb
    delta_safe = dr.maximum(delta, 1e-7)
    max_rgb_safe = dr.maximum(max_rgb, 1e-7)

    R, G, B = rgb.x, rgb.y, rgb.z

    h = dr.zeros(mi.Float)
    h = dr.select((R >= G) & (G >= B), 60 * (G - B) / delta_safe, h)
    h = dr.select((G >= R) & (R >= B), 60 * (2.0 - (R - B) / delta_safe), h)
    h = dr.select((G >= B) & (B >= R), 60 * (2.0 + (B - R) / delta_safe), h)
    h = dr.select((B >= G) & (G >= R), 60 * (4.0 - (G - R) / delta_safe), h)
    h = dr.select((B >= R) & (R >= G), 60 * (4.0 + (R - G) / delta_safe), h)
    h = dr.select((R >= B) & (B >= G), 60 * (6.0 - (B - G) / delta_safe), h)
    h = dr.select(delta == 0, 0.0, h)

    return mi.Color3f(h, delta / max_rgb_safe, max_rgb)

def _mod(a, b):
    return a - b * dr.floor(a / b)

def hsv2rgb(hsv):
    chroma = hsv.y * hsv.z
    h6 = hsv.x / 60.0
    x = chroma * (1.0 - dr.abs(_mod(h6, 2.0) - 1.0))
    m = hsv.z - chroma

    rgb = mi.Color3f(0, 0, 0)
    rgb = dr.select((h6 >= 0.0) & (h6 < 1.0), mi.Color3f(chroma, x, 0), rgb)
    rgb = dr.select((h6 >= 1.0) & (h6 < 2.0), mi.Color3f(x, chroma, 0), rgb)
    rgb = dr.select((h6 >= 2.0) & (h6 < 3.0), mi.Color3f(0, chroma, x), rgb)
    rgb = dr.select((h6 >= 3.0) & (h6 < 4.0), mi.Color3f(0, x, chroma), rgb)
    rgb = dr.select((h6 >= 4.0) & (h6 < 5.0), mi.Color3f(x, 0, chroma), rgb)
    rgb = dr.select((h6 >= 5.0) & (h6 < 6.0), mi.Color3f(chroma, 0, x), rgb)
    return rgb + m


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

        def traverse(self, callback):
            callback.put_object('hue',        self.hue,        +mi.ParamFlags.Differentiable)
            callback.put_object('saturation', self.saturation, +mi.ParamFlags.Differentiable)
            callback.put_object('value',      self.value,      +mi.ParamFlags.Differentiable)
            callback.put_object('mix',        self.mix,        +mi.ParamFlags.Differentiable)
            callback.put_object('input',      self.input,      +mi.ParamFlags.Differentiable)


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

    mi.register_texture('hue_saturation_value', HueSaturationValue)
