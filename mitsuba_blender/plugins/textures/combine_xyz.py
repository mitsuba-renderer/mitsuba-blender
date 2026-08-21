from __future__ import annotations

from typing import TYPE_CHECKING
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

    class CombineXYZ(mi.Texture):
        ''' Texture combining three values into a vector'''
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

        def is_spatially_varying(self):
            return (self.x.is_spatially_varying() or
                    self.y.is_spatially_varying() or
                    self.z.is_spatially_varying())

        def to_string(self):
            return (f'CombineXYZ[x = {self.x},\n y = {self.y},\n z = {self.z}]')

    mi.register_texture('combine_xyz', CombineXYZ)
