from __future__ import annotations

from typing import TYPE_CHECKING
from enum import Enum
from .common import get_texture, hsv2rgb, rgb2hsv

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

    class HueSaturationValue(mi.Texture):
        ''' Hue-Saturation-Value texture.

        Convert to HSV, offsets hue, scales saturation and value, converter
        back, then lerps towards the resuly by Fac. The conversions follow
        hsv_to_rgb and rgb_to_hsv in Blender's math_color.cc, which are branchless
        and take hue in [0, 1] rather than degrees.
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
            hsv.x = hsv.x + hue + 0.5
            hsv.x = hsv.x - dr.floor(hsv.x)
            hsv.y = dr.clip(hsv.y * saturation, 0.0, 1.0)
            hsv.z = hsv.z * value

            return dr.maximum(dr.lerp(color, hsv2rgb(hsv), mix), 0.0)

        def mean(self):
            return 0.5

        def traverse(self, callback):
            callback.put_object('hue',        self.hue,        +mi.ParamFlags.Differentiable)
            callback.put_object('saturation', self.saturation, +mi.ParamFlags.Differentiable)
            callback.put_object('value',      self.value,      +mi.ParamFlags.Differentiable)
            callback.put_object('mix',        self.mix,        +mi.ParamFlags.Differentiable)
            callback.put_object('input',      self.input,      +mi.ParamFlags.Differentiable)


    mi.register_texture('hue_saturation_value', HueSaturationValue)
