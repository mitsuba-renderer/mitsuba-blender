from __future__ import annotations
from typing import TYPE_CHECKING
from enum import Enum
from .common import get_texture

if TYPE_CHECKING:
    import mitsuba as mi
    import drjit as dr


def register(mi, dr): 
    class InvertColor(mi.Texture):
        '''
        Invert color texture
        '''
        def __init__(self, props: mi.Properties) -> None:
            super().__init__(props)

            self.input = get_texture(props, 'color', 1.0)
            self.fac = get_texture(props, 'fac', 1.0)

        def _process(self, value, si, active=True):
            f = dr.clip(self.fac.eval_1(si, active), 0.0, 1.0)
            inv_val = 1.0 - value
            return dr.lerp(value, inv_val, f)


        def traverse(self, cb):
            cb.put_object('color', self.input, mi.ParamFlags.Differentiable)
            cb.put_object('fac', self.fac, mi.ParamFlags.Differentiable)

        def eval(self, si, active=True):
            return self.eval_3(si, active)
        
        def eval_1(self, si, active=True):
            return self._process(self.input.eval_1(si, active), si, active)

        def eval_3(self, si, active=True):
            return self._process(self.input.eval_3(si, active), si, active)

        def mean(self):
            return 0.5

    
    mi.register_texture('invert', InvertColor)
