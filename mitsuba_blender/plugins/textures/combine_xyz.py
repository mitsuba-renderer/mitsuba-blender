
from __future__ import annotations

from typing import TYPE_CHECKING
from enum import Enum
from .common import get_texture

if TYPE_CHECKING:
    import mitsuba as mi
    import drjit as dr


def register(mi, dr):

    class CombineXYZ(mi.Texture):
        def __init__(self, props: mi.Properties):
            super().__init__(props)
            self.x = get_texture(props, 'x', 0.0)
            self.y = get_texture(props, 'y', 0.0)
            self.z = get_texture(props, 'z', 0.0)


        def eval(self, si, active=True):
            return mi.UnpolarizedSpectrum(self.eval_3(si, active))

        def eval_1(self, si, active=True):
            c = self.eval_3(si, active)
            return (c.x + c.y + c.z) * (1.0 / 3.0)


        def eval_3(self, si, active=True):
            return mi.Color3f(self.x.eval_1(si, active),
                              self.y.eval_1(si, active),
                              self.z.eval_1(si, active))

        def mean(self):
            return 0.5

        def traverse(self, cb):
            cb.put('x', self.x, mi.ParamFlags.Differentiable)
            cb.put('y', self.y, mi.ParamFlags.Differentiable)
            cb.put('z', self.z, mi.ParamFlags.Differentiable)

    mi.register_texture('combine_xyz', CombineXYZ)
