from __future__ import annotations # Delayed parsing of type annotations
from enum import Enum

import mitsuba as mi
import drjit as dr

from .common import get_texture

class ColorRamp(mi.Texture):
    '''
    Mapping of an input texture's relative luminance to colors on an RGB gradient
    '''
    class InterpolationMode(Enum):
        Linear = 0,
        Ease = 1,
        Constant = 2,
        Cardinal = 3,

    def __init__(self, props):
        mi.Texture.__init__(self, props)

        self.input = get_texture(props,'input')

        # Load interpolation mode
        mode_str = props.get('mode', 'linear')
        if mode_str == 'linear':
            self.mode = ColorRamp.InterpolationMode.Linear
        elif mode_str == 'ease':
            self.mode = ColorRamp.InterpolationMode.Ease
        elif mode_str == 'constant':
            self.mode = ColorRamp.InterpolationMode.Constant
        elif mode_str == 'cardinal':
            self.mode = ColorRamp.InterpolationMode.Cardinal
        else:
            raise NotImplementedError('Interpolation mode {mode_str} is not supported')
        self.mode_str = mode_str

        # Load colors and positions
        num_bands = props.get('num_bands')
        if num_bands <= 0:
            raise Exception(f'Number of color bands {num_bands} has to be strictly positive')

        padding = 2
        self.band_pos   = dr.zeros(mi.Float, num_bands + padding)
        self.band_col   = dr.zeros(mi.Float, 3 * (num_bands + padding))

        prev_pos = 0
        for i in range(num_bands):
            pos = props.get(f'pos{i}')
            col = props.get(f'color{i}')

            if pos < 0 or pos > 1:
                raise Exception(f'Position at index {i} has value {pos} outside range [0,1]')

            if pos < prev_pos:
                raise Exception(f'Position at index {i} has value {pos} less than' +
                                f'previous position {prev_pos} however sequence ' +
                                'needs to be increasing')

            prev_pos = pos
            self.band_pos[i+1] = pos
            self.band_col[3*(i+1)  ] = col[0]
            self.band_col[3*(i+1)+1] = col[1]
            self.band_col[3*(i+1)+2] = col[2]

        # Left-pad colors
        self.band_pos[0] = 0
        self.band_col[0] = self.band_col[3]
        self.band_col[0] = self.band_col[4]
        self.band_col[0] = self.band_col[5]

        # Right-pad colors
        self.band_pos[num_bands + padding - 1] = 1.0
        last_elem = num_bands + padding - 1
        self.band_col[3*last_elem  ] = self.band_col[3*(last_elem-1)]
        self.band_col[3*last_elem+1] = self.band_col[3*(last_elem-1)+1]
        self.band_col[3*last_elem+2] = self.band_col[3*(last_elem-1)+2]


    def traverse(self, callback):
        callback.put_object('input', self.input, mi.ParamFlags.Differentiable)

    def parameters_changed(self, keys):
        pass

    def eval(self, si, active):
        return self.eval_3(si, active)

    def eval_1(self, si, active):
        return mi.luminance(self.process(self.input.eval_1(si, active), active))

    def eval_3(self, si, active):
        return self.process(self.input.eval_1(si, active), active)

    def process(self, input_pos, active):
        # This includes the left and right padding
        num_bands = len(self.band_pos)

        # We start search at index 1 because we have padded band pos/colors
        # This ensures we don't have to do any index out-of-bounds checks 
        upper_band_idx = dr.binary_search(1, num_bands - 1,
            lambda idx: dr.gather(mi.Float, self.band_pos, idx, active) <= input_pos)
 
        lower_band_idx = upper_band_idx - 1

        pos0 = dr.gather(mi.Float, self.band_pos, lower_band_idx, active)
        pos1 = dr.gather(mi.Float, self.band_pos, upper_band_idx, active)
        relative_fac = dr.select(pos0 != pos1,
            (input_pos - pos0) / (pos1 - pos0), 0)
        relative_fac = dr.clip(relative_fac, 0, 1)

        colors  = [mi.Color3f(0)] * 4
        weights = [mi.Float(0)] * 4

        colors[1] = dr.gather(mi.Color3f, self.band_col, lower_band_idx, active)
        colors[2] = dr.gather(mi.Color3f, self.band_col, upper_band_idx, active)

        if self.mode == ColorRamp.InterpolationMode.Cardinal:
            # Left control point
            colors[0] = dr.select(lower_band_idx > 0,
                dr.gather(mi.Color3f, self.band_col, lower_band_idx - 1, active), colors[1])
            # Right control point
            colors[3] = dr.select(upper_band_idx < num_bands - 1,
                dr.gather(mi.Color3f, self.band_col, upper_band_idx + 1, active), colors[2])

        def mix_colors(start_idx, count) -> mi.Color3f:
            out = mi.Color3f(0)
            for i in range(start_idx, start_idx + count):
                out += colors[i] * weights[i]
            return out

        if self.mode == ColorRamp.InterpolationMode.Linear:
            weights[1] = 1.0 - relative_fac
            weights[2] = relative_fac
            out = mix_colors(start_idx=1, count=2)
        elif self.mode == ColorRamp.InterpolationMode.Ease:
            ease_fac = relative_fac * relative_fac * (3.0 - 2.0 * relative_fac)
            weights[1] = 1.0 - ease_fac
            weights[2] = ease_fac
            out = mix_colors(start_idx=1, count=2)
        elif self.mode == ColorRamp.InterpolationMode.Constant:
            weights[1] = 1.0
            out = mix_colors(start_idx=1, count=1)
        elif self.mode == ColorRamp.InterpolationMode.Cardinal:
            t = relative_fac
            t2 = t * t
            t3 = t2 * t
            fc = 0.71
            weights[0] = -fc * t3 + 2.0 * fc * t2 - fc * t
            weights[1] = (2.0 - fc) * t3 + (fc - 3.0) * t2 + 1.0
            weights[2] = (fc - 2.0) * t3 + (3.0 - 2.0 * fc) * t2 + fc * t
            weights[3] = fc * t3 - fc * t2
            out = mix_colors(start_idx=0, count=4)
        else:
            raise NotImplementedError(f'Interpolation mode {self.mode_str} is not supported')

        return out

    def mean(self):
        raise NotImplementedError

    def resolution(self):
        return self.input.resolution()

    def spectral_resolution(self):
        pass

    def wavelength_range(self):
        return mi.ScalarVector2f(mi.MI_CIE_MIN, mi.MI_CIE_MAX)

    def is_spatially_varying(self):
        return self.input.is_spatially_varying()

    def to_string(self):
        return f'ColorRamp[input={self.input}, mode={self.mode_str}]'

mi.register_texture('color_ramp', ColorRamp)
