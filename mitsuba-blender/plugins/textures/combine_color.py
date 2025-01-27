from __future__ import annotations # Delayed parsing of type annotations

import drjit as dr
import mitsuba as mi

from .common import get_texture

class CombineColor(mi.Texture):
    '''
    RGB to BW texture.
    '''
    def __init__(self, props):
        mi.Texture.__init__(self, props)
        self.mode = props.get('mode', 'RGB')
        assert self.mode == 'RGB', self.mode
        self.R = get_texture(props, 'red', 0.0)
        self.G = get_texture(props, 'green', 0.0)
        self.B = get_texture(props, 'blue', 0.0)

    def traverse(self, callback):
        callback.put_object('R', self.R, +mi.ParamFlags.Differentiable)
        callback.put_object('G', self.G, +mi.ParamFlags.Differentiable)
        callback.put_object('B', self.B, +mi.ParamFlags.Differentiable)

    def parameters_changed(self, keys):
        pass

    def eval(self, si, active):
        return self.eval_3(si, active)

    def eval_3(self, si, active):
        return mi.Color3f(
            self.R.eval_1(si, active),
            self.G.eval_1(si, active),
            self.B.eval_1(si, active)
        )

    def mean(self):
        return self.color.mean() # TODO this is wrong

    def resolution(self):
        return mi.ScalarVector2i(1, 1)

    def spectral_resolution(self):
        pass

    def wavelength_range(self):
        return mi.ScalarVector2f(mi.MI_CIE_MIN, mi.MI_CIE_MAX)

    def is_spatially_varying(self):
        return any([t.is_spatially_varying() for t in [self.R, self.G, self.B]])

    def to_string(self):
        return f'CombineColor[mode={self.mode}, R={self.R}, G={self.G}, B={self.B}]'

mi.register_texture('combine_color', CombineColor)
