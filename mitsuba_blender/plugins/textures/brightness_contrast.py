from __future__ import annotations

from typing import TYPE_CHECKING
from enum import Enum
from .common import get_texture

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
    class BrightnessContrast(mi.Texture):
        ''' Bright/Contrast texture

        Follows node_shader_brightness.cc: gain is 1 + constant, offset is
        brightness - contrast/2 - constrast*0.5... , and the result is clamped
        to zero from below
        '''

        def __init__(self, props : mi.Properties) -> None:
            super().__init__(props)
            self.input = get_texture(props, 'color', 1.0)
            self.brightness = get_texture(props, 'brightness', 0.0)
            self.contrast = get_texture(props, 'contrast', 0.0)

        def _process(self, value, si, active):
            bright = self.brightness.eval_1(si, active)
            contrast = self.contrast.eval_1(si, active)

            a = 1.0 + contrast
            b = bright - contrast * 0.5
            return dr.maximum(a * value + b, 0.0)

        def eval(self, si, active=True):
            return self.eval_3(si, active)

        def eval_1(self, si, active=True):
            return self._process(self.input.eval_1(si, active), si, active)

        def eval_3(self, si, active=True):
            return self._process(self.input.eval_3(si, active), si, active)

        def mean(self):
            return 0.5

        def traverse(self, cb):
            cb.put_object('input', self.input, mi.ParamFlags.Differentiable)
            cb.put_object('brightness', self.brightness, mi.ParamFlags.Differentiable)
            cb.put_object('contrast', self.contrast, mi.ParamFlags.Differentiable)

    mi.register_texture('brightness_contrast', BrightnessContrast)
