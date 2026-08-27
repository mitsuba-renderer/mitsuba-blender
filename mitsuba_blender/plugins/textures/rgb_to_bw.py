from __future__ import annotations

from typing import TYPE_CHECKING

from .common import get_texture
import drjit as dr

if TYPE_CHECKING:
    import mitsuba as mi
    import drjit as dr




_REC709 = (0.2126, 0.7152, 0.0722)


def register(mi, dr):
    '''
    Define and register the plugin for the active variant

    mi.Texture is a different class per variant, so a class defined at
    module scope would bind to whichever variant was active on first
    import and never rebind. Defining it inside this factory means
    register_plugins() can be called again after every set_variant.
    The class body should not be moved out of this function.
    '''

    class RGBToBW(mi.Texture):
        ''' Color to gray scale converter

        Texture which convert an RGB color input into a black and white
        (grayscale) value, using a weighted formula (_REC709).
        '''
        def __init__(self, props: mi.Properties) -> None:
            super().__init__(props)

            self.color = get_texture(props, 'color')

        def _luminance(self, si, active):
            c = self.color.eval_3(si, active)
            return _REC709[0] * c.x + _REC709[1] * c.y + _REC709[2] * c.z

        def eval(self, si, active=True):
            return mi.UnpolarizedSpectrum(self._luminance(si, active))

        def eval_1(self, si, active=True):
            return self._luminance(si, active)

        def eval_3(self, si, active=True):
            lum = self._luminance(si, active)
            return mi.Color3f(lum, lum, lum)

        def mean(self):
            return 0.5

        def traverse(self, cb):
            cb.put('color', self.color, mi.ParamFlags.Differentiable)

        def parameters_changed(self, keys=None):
            pass

        def is_spatially_varying(self):
            return self.color.is_spatially_varying()

        def to_string(self):
            return (f'RGBToBW[color = {self.color}]')


    mi.register_texture('rgb_to_bw', RGBToBW)
