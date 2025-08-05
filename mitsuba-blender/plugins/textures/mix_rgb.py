from __future__ import annotations # Delayed parsing of type annotations
from enum import Enum

import mitsuba as mi
import drjit as dr

from .common import get_texture

class MixMode(Enum):
    Blend = 0,
    Add = 1,
    Multiply = 2,
    Subtract = 3,
    Difference = 4,
    Exclusion = 5,
    Darken = 6,
    Lighten = 7,
    Overlay = 8

class MixRGB(mi.Texture):
    '''
    Color mixing of two input textures given a factor
    '''
    def __init__(self, props):
        mi.Texture.__init__(self, props)
        self.color0 = get_texture(props,'color0')
        self.color1 = get_texture(props,'color1')
        self.factor = get_texture(props,'factor', 0.5)

        mode_str = props.get('mode', 'blend')

        if mode_str == 'blend':
            self.mode = MixMode.Blend
        elif mode_str == 'lighten':
            self.mode = MixMode.Lighten
        elif mode_str == 'darken':
            self.mode = MixMode.Darken
        elif mode_str == 'multiply':
            self.mode = MixMode.Multiply
        elif mode_str == 'subtract':
            self.mode = MixMode.Subtract
        elif mode_str == 'difference':
            self.mode = MixMode.Difference
        elif mode_str == 'overlay':
            self.mode = MixMode.Overlay
        elif mode_str == 'exclusion':
            self.mode = MixMode.Exclusion
        elif mode_str == 'add':
            self.mode = MixMode.Add
        else:
            raise NotImplementedError(f'Mix mode {mode_str} is not supported')

        self.mode_str = mode_str

    def traverse(self, callback):
        callback.put_object('color0', self.color0, mi.ParamFlags.Differentiable)
        callback.put_object('color1', self.color1, mi.ParamFlags.Differentiable)
        callback.put_object('factor', self.factor, mi.ParamFlags.Differentiable)

    def parameters_changed(self, keys):
        pass

    def eval(self, si, active):
        return self.eval_3(si, active)

    def eval_1(self, si, active):
        return self.process(
            self.color0.eval_1(si, active),
            self.color1.eval_1(si, active),
            si, active)

    def eval_3(self, si, active):
        return self.process(
            self.color0.eval_3(si, active),
            self.color1.eval_3(si, active),
            si, active)

    def process(self, col0, col1, si, active):
        fac = self.factor.eval_1(si, active)

        def mix(a, b):
            return dr.lerp(a, b, fac)

        mode = self.mode

        if mode == MixMode.Blend:
            out = mix(col0, col1)
        elif mode == MixMode.Add:
            out = mix(col0, col0 + col1)
        elif mode == MixMode.Multiply:
            out = mix(col0, col0 * col1)
        elif mode == MixMode.Subtract:
            out = mix(col0, col0 - col1)
        elif mode == MixMode.Difference:
            out = mix(col0, dr.abs(col0 - col1))
        elif mode == MixMode.Exclusion:
            out = dr.maximum(mix(col0, col0 + col1 - 2.0 * col0 * col1), 0)
        elif mode == MixMode.Darken:
            out = mix(col0, dr.minimum(col0, col1))
        elif mode == MixMode.Lighten:
            out = mix(col0, dr.maximum(col0, col1))
        elif mode == MixMode.Overlay:
            t = fac
            tm = 1.0 - fac
            out = col0
            out = dr.select(out < 0.5,
                out * (tm + 2.0 * t * col1),
                1.0 - (tm + 2.0 * t * (1.0 - col1)) * (1.0 - out))
        else:
            raise NotImplementedError(f'Mix mode {self.mode_str} is not supported')

        return out

    def mean(self):
        raise NotImplementedError

    def resolution(self):
        return self.color0.resolution()

    def spectral_resolution(self):
        pass

    def wavelength_range(self):
        return mi.ScalarVector2f(mi.MI_CIE_MIN, mi.MI_CIE_MAX)

    def is_spatially_varying(self):
        return any([t.is_spatially_varying() for t in [
            self.color0, self.color1, self.factor
        ]])

    def to_string(self):
        return f'MixRGB[color0={self.color0}, color1={self.color1}, factor={self.factor}, mode={self.mode_str}]'

mi.register_texture('mix_rgb', MixRGB)
