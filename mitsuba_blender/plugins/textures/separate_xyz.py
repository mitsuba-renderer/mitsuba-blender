from __future__ import annotations

from typing import TYPE_CHECKING

import drjit as dr
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

    class SeparateXYZ(mi.Texture):
        ''' One component of a vector-valued texture

        Blender's Separate XYZ node has three outputs; each becomes
        its own instance with a different index, since Mitsuba texture
        has one output.
        '''

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

        def to_string(self):
            return (f'SeparateXYZ[vector = {self.vector},\n index = {self.index}\n]')

    mi.register_texture('separate_xyz', SeparateXYZ)
