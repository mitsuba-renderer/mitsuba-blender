from __future__ import annotations

from typing import TYPE_CHECKING

import drjit as dr
import mitsuba as mi

from .common import get_texture, rgb2hsl,rgb2hsv

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

    class SeparateColor(mi.Texture):
        ''' One component of a color-valued texture

        Blender's Separate Color node has three outputs; each becomes
        its own instance with a different index, since Mitsuba texture
        has one output.
        '''
        def __init__(self, props: mi.Properties) -> None:
            super().__init__(props)

            self.color = get_texture(props, 'color', 0.0)
            self.index = int(props.get('index', 0))
            self.mode = props.get('mode', 'RGB')

        def eval(self, si, active=True):
            return mi.UnpolarizedSpectrum(self.eval_1(si, active))

        def eval_1(self, si, active=True):
            c = self.color.eval_3(si, active)
            if self.mode == 'HSV':
                c = rgb2hsv(c)
            elif self.mode == 'HSL':
                c = rgb2hsl(c)
            return [c.x, c.y, c.z][self.index]


        def eval_3(self, si, active=True):
            c = self.eval_1(si, active)
            return mi.Color3f(c, c, c)


        def mean(self):
            return 0.5

        def traverse(self, cb):
            cb.put_object('color', self.color, mi.ParamFlags.Differentiable)

        def to_string(self):
            return f'SeparateColor[index={self.index}, mode={self.mode}]'

    mi.register_texture('separate_color', SeparateColor)

