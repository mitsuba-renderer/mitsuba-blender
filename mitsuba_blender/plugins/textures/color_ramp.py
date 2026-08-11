from __future__ import annotations
from typing import TYPE_CHECKING
from enum import Enum
from .common import get_texture

if TYPE_CHECKING:
    import mitsuba as mi
    import drjit as dr


def register(mi, dr):
    class ColorRamp(mi.Texture):
        '''
        ColorRamp texture plugin

        This has been taken from Sebastien Speierer and Baptiste Nicolet PR#121. It has been adapted
        by being created inside register() rather than at import time
        '''

        class InterpolationMode(Enum):
            Linear = 0,
            Ease = 1,
            Constant = 2,
            Cardinal = 3,

        def __init__(self, props: mi.Properties) -> None:
            super().__init__(props)


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
            self.band_pos = [0.0] * (num_bands + padding)
            self.band_col = [0.0] * (3 * (num_bands + padding))

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
            self.band_col[0] = self.band_col[3]
            self.band_col[1] = self.band_col[4]
            self.band_col[2] = self.band_col[5]

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

        def eval_1_grad(self, si, active=True):
            return mi.Vector2f(0.0)

        def eval_3(self, si, active):
            return self.process(self.input.eval_1(si, active), active)

        def process(self, input_pos, active=True):
            col = mi.Color3f(self.band_col[0], self.band_col[1], self.band_col[2])
            for i in range(1, len(self.band_pos)):
                lo, hi = self.band_pos[i-1], self.band_pos[i]
                t = dr.clip((input_pos - lo) / max(hi - lo, 1e-8), 0.0, 1.0)
                c0 = mi.Color3f(*self.band_col[3*(i-1):3*i])
                c1 = mi.Color3f(*self.band_col[3*i:3*(i+1)])
                col = dr.select(input_pos >= lo, dr.lerp(c0, c1, t), col)
            return col

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
    print('Reigstered')
    mi.register_texture('color_ramp', ColorRamp)

