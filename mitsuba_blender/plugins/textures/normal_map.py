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

    class NormalMapWrapper(mi.Texture):
        ''' Wrapper of the NormalMap BSDF

        It allows to add a `strength` factor to the normal map.
        '''

        def __init__(self, props : mi.Properties) -> None:
            super().__init__(props)

            self.texture = get_texture(props, 'texture', 1.0)
            self.strength = get_texture(props, 'strength', 1.0)

        def eval(self, si, active=True):
            return mi.UnpolarizedSpectrum(self.eval_3(si, active))

        def eval_1(self, si, active=True):
            c = self.eval_3(si, active)
            return (c.x + c.y + c.z) * (1.0/3.0)

        def eval_3(self, si, active=True):
            n = self.texture.eval_3(si, active) * 2.0 - 1.0
            s = self.strength.eval_1(si, active)
            n = mi.Color3f(n.x * s, n.y * s, dr.lerp(1.0, n.z, dr.clip(s, 0.0, 1.0)))

            return n * 0.5 + 0.5

        def traverse(self, cb: mi.TraversalCallback):
            cb.put('texture', self.texture, mi.ParamFlags.Differentiable)
            cb.put('strength', self.strength, mi.ParamFlags.Differentiable)

        def parameters_changed(self, keys=None):
            pass

        def is_spatially_varying(self):
            return (self.texture.is_spatially_varying() or
                    self.strength.is_spatially_varying())

        def mean(self):
            return 0.5


    mi.register_texture('normal_map', NormalMapWrapper)
