
from __future__ import annotations

from typing import TYPE_CHECKING
from enum import Enum
from .common import get_texture, hsv2rgb, hsl2rgb

if TYPE_CHECKING:
    import mitsuba as mi
    import drjit as dr


def register(mi, dr):

    class CombineColor(mi.Texture):
        def __init__(self, props: mi.Properties):
            super().__init__(props)

            self.red = get_texture(props, 'red', 0.0)
            self.green = get_texture(props, 'green', 0.0)
            self.blue = get_texture(props, 'blue', 0.0)
            self.mode = props.get('mode', 'RGB')


        def eval(self, si, active=True):
            return mi.UnpolarizedSpectrum(self.eval_3(si, active))

        def eval_1(self, si, active=True):
            c = self.eval_3(si, active)

        def eval_3(self, si, active=True):
            color = mi.Color3f(self.red.eval_1(si, active),
                              self.green.eval_1(si, active),
                              self.blue.eval_1(si, active))
            if self.mode == 'HSV':
                return hsv2rgb(color)
            elif self.mode == 'HSL':
                return hsl2rgb(color)
            return color

            return (c.x + c.y + c.z) * (1.0 / 3.0)

        def mean(self):
            return 0.5

        def traverse(self, cb: mi.TraversalCallback):
            cb.put('red', self.red, mi.ParamFlags.Differentiable)
            cb.put('green', self.green, mi.ParamFlags.Differentiable)
            cb.put('blue', self.blue, mi.ParamFlags.Differentiable)


    mi.register_texture('combine_color', CombineColor)
