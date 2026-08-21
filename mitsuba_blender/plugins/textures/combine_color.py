from __future__ import annotations

from typing import TYPE_CHECKING
from .common import get_texture, hsv2rgb, hsl2rgb

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

    class CombineColor(mi.Texture):
        ''' Texture combining inputs into a color

        Converts three value, red, green, blue into a color, either
        in RGB, HSV or HSL.
        '''
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

        def is_spatially_varying(self):
            return (self.red.is_spatially_varying() or
                    self.green.is_spatially_varying() or
                    self.blue.is_spatially_varying())

        def to_string(self):
            return (f'CombineColor[mode = {self.mode},\n'
                    f'red = {self.red},\n'
                    f'green = {self.green},\n'
                    f'blue = {self.blue}\n]')


    mi.register_texture('combine_color', CombineColor)
