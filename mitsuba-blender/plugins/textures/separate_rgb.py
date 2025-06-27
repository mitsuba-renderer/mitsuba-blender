from __future__ import annotations # Delayed parsing of type annotations
from typing import Tuple

import drjit as dr
import mitsuba as mi

class SeparateRGB(mi.Texture):
    '''
    Helper texture plugin to separate an RGB texture into its components.

    Parameters:
        - channel: The channel to extract (default: r)
        - input: The input texture
    '''
    def __init__(self, props):
        mi.Texture.__init__(self, props)
        self.texture = props.get('input')
        self.channel = props.get('channel', 'r')
        if self.channel not in ['r', 'g', 'b']:
            raise ValueError(f"SeparateRGB: Invalid channel {self.channel}")

    def traverse(self, callback):
        callback.put_object('input', self.texture, mi.ParamFlags.Differentiable)

    def parameters_changed(self, keys):
        self.texture.parameters_changed(keys)

    def _eval_channel(self, si, active):
        color = self.texture.eval(si, active)
        return color[{ 'r': 0, 'g': 1, 'b': 2 }[self.channel]]

    def eval(self, si, active):
        return self._eval_channel(si, active)

    def eval_1(self, si, active):
        return self._eval_channel(si, active)

    def eval_3(self, si, active):
        return self._eval_channel(si, active)

    def sample_spectrum(self, si, sample, active):
        return self.texture.sample_spectrum(si, sample, active)

    def pdf_spectrum(self, si, active):
        return self.texture.pdf_spectrum(si, active)

    def sample_position(self, sample, active):
        return self.texture.sample_position(sample, active)

    def pdf_position(self, p, active):
        return self.texture.pdf_position(p, active)

    def mean(self):
        return self.texture.mean()

    def resolution(self):
        return self.texture.resolution()

    def spectral_resolution(self):
        return self.texture.spectral_resolution()

    def wavelength_range(self):
        return self.texture.wavelength_range()

    def is_spatially_varying(self):
        return self.texture.is_spatially_varying()

    def to_string(self):
        return f'Separate RGB[input={self.texture}, channel={self.channel}]'

mi.register_texture('separate_rgb', SeparateRGB)
