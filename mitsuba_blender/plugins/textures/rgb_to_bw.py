from __future__ import annotations
from typing import TYPE_CHECKING
from .common import get_texture

import drjit as dr

if TYPE_CHECKING:
    import mitsuba as mi
    import drjit as dr




_REC709 = (0.2126, 0.7152, 0.0722)


def register(mi, dr):
    class RGBToBW(mi.Texture):
        def __init__(self, props: mi.Properties) -> None:
            super().__init__(props)

            self.color = get_texture(props, 'color')

        def _luminance(self, si, active):
            c = self.color.eval_3(si, active)
            return _REC709[0] * c.x + _REC709[1] * c.y + _REC709[2] * c.z


        def eval_1(self, si, active=True):
            return self._luminance(si, active)

        def eval_3(self, si, active=True):
            lum = self._luminance(si, active)
            return mi.Color3f(lum, lum, lum)

        def eval(self, si, active=True):
            return mi.UnpolarizedSpectrum(self._luminance(si, active))

    mi.register_texture('rgb_to_bw', RGBToBW)
