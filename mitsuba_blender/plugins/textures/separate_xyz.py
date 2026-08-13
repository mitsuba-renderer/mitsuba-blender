
from __future__ import annotations
from typing import TYPE_CHECKING

import drjit as dr

from .common import get_texture

if TYPE_CHECKING:
    import mitsuba as mi
    import drjit as dr


def register(mi, dr):
    class SeparateXYZ(mi.Texture):
        def __init__(self, props : mi.Properties):
            super().__init__(props)
            self.vector = get_texture(props, 'vector', 0.0)
            self.index = int(props.get('index', 0.0))

        def eval(self, si, active=True):
            return mi.UnpolarizedSpectrum(self.eval_1(si, active))

        def eval_1(self, si, active=True):
            v = self.vector.eval_3(si, active)
            return [v.x, v.y, v.z][self.index]

        def eval_3(self, si, active=True):
            c = self.eval_1(si, active)
            return mi.Color3f(c, c, c)


        def mean(self):
            return 0.5

        def traverse(self, cb):
            cb.put('vector', self.vector, mi.ParamFlags.Differentiable)
            cb.put('index', self.index, mi.ParamFlags.Differentiable)

    mi.register_texture('separate_xyz', SeparateXYZ)
