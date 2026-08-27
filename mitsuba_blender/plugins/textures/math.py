from __future__ import annotations

from typing import TYPE_CHECKING

from .common import get_texture
import drjit as dr

if TYPE_CHECKING:
    import mitsuba as mi
    import drjit as dr

# Math texture operations
def _clamp(v, lo=0.0, hi=1.0):
    return dr.clip(v, lo, hi)

def _safe_divide(a, b):
    return dr.select(b != 0.0, a / dr.select(b != 0.0, b, 1.0), 0.0)


def _safe_power(a, b):
    is_int_exp = dr.floor(b) == b
    valid = (a >= 0.0) | is_int_exp
    mag = dr.power(dr.abs(a), b)
    odd = is_int_exp & (dr.floor(b * 0.5) * 2.0 != b)
    signed = dr.select((a < 0.0) & odd, -mag, mag)
    return dr.select(valid, signed, 0.0)

def _safe_log(a, b):
    valid = (a > 0.0) & (b > 0.0) & (b != 1.0)
    sa = dr.select(a > 0.0, a, 1.0)
    sb = dr.select((b > 0.0) & (b != 1.0), b, 2.0)
    return dr.select(valid, dr.log(sa) / dr.log(sb), 0.0)

def _fract(a):
    return a - dr.floor(a)

def _wrap(a, b, c):
    rng = b - c
    safe = dr.select(rng != 0.0, rng, 1.0)
    return dr.select(rng != 0.0, a - rng * dr.floor((a - c) / safe), c)

def _pingpong(a, b):
    sb = dr.select(b != 0.0, b, 1.0)
    val = dr.abs(_fract((a - sb) / (dr.maximum(sb * 2.0, 1e-8))) * sb * 2.0 - sb)
    return dr.select(b != 0.0, val, 0.0)

def _smooth_min(a, b, k):
    sk = dr.select(k != 0.0, k, 1.0)
    h = dr.maximum(sk - dr.abs(a - b), 0.0) / sk
    return dr.select(k != 0.0,
                     dr.minimum(a, b) - h*h*h*sk*(1.0/6.0),
                     dr.minimum(a, b))


_MATH_OPS = {
    'ADD':            lambda a, b, c: a + b,
    'SUBTRACT':       lambda a, b, c: a - b,
    'MULTIPLY':       lambda a, b, c: a * b,
    'DIVIDE':         lambda a, b, c: _safe_divide(a, b),
    'MULTIPLY_ADD':   lambda a, b, c: a * b + c,
    'POWER':          lambda a, b, c: _safe_power(a, b),
    'LOGARITHM':      lambda a, b, c: _safe_log(a, b),
    'SQRT':           lambda a, b, c: dr.select(
                            a >= 0.0,
                            dr.sqrt(dr.maximum(a, 0.0)), 0.0),
    'INVERSE_SQRT':   lambda a, b, c: dr.select(
                            a > 0.0,
                            1.0 / dr.sqrt(dr.maximum(a, 1e-8)), 0.0),
    'ABSOLUTE':       lambda a, b, c: dr.abs(a),
    'EXPONENT':       lambda a, b, c: dr.exp(a),
    'MINIMUM':        lambda a, b, c: dr.minimum(a, b),
    'MAXIMUM':        lambda a, b, c: dr.maximum(a, b),
    'LESS_THAN':      lambda a, b, c: dr.select(a < b, 1.0, 0.0),
    'GREATER_THAN':   lambda a, b, c: dr.select(a > b, 1.0, 0.0),
    'SIGN':           lambda a, b, c: dr.select(a > 0.0, 1.0,
                                       dr.select(a < 0.0, -1.0, 0.0)),
    'COMPARE':        lambda a, b, c: dr.select(
                          dr.abs(a - b) <= dr.maximum(c, 1e-5), 1.0, 0.0),
    'SMOOTH_MIN':     lambda a, b, c: _smooth_min(a, b, c),
    'SMOOTH_MAX':     lambda a, b, c: -_smooth_min(-a, -b, c),
    'ROUND':          lambda a, b, c: dr.floor(a + 0.5),
    'FLOOR':          lambda a, b, c: dr.floor(a),
    'CEIL':           lambda a, b, c: dr.ceil(a),
    'TRUNC':          lambda a, b, c: dr.trunc(a),
    'FRACT':          lambda a, b, c: _fract(a),
    'MODULO':         lambda a, b, c: dr.select(
                          b != 0.0,
                          a - dr.trunc(a / dr.select(b != 0.0, b, 1.0))
                            * dr.select(b != 0.0, b, 1.0), 0.0),
    'FLOORED_MODULO': lambda a, b, c: dr.select(
                          b != 0.0,
                          a - dr.floor(a / dr.select(b != 0.0, b, 1.0))
                            * dr.select(b != 0.0, b, 1.0), 0.0),
    'WRAP':           lambda a, b, c: _wrap(a, b, c),
    'SNAP':           lambda a, b, c: dr.floor(_safe_divide(a, b)) * b,
    'PINGPONG':       lambda a, b, c: _pingpong(a, b),
    'SINE':           lambda a, b, c: dr.sin(a),
    'COSINE':         lambda a, b, c: dr.cos(a),
    'TANGENT':        lambda a, b, c: dr.tan(a),
    'ARCSINE':        lambda a, b, c: dr.asin(_clamp(a, -1.0, 1.0)),
    'ARCCOSINE':      lambda a, b, c: dr.acos(_clamp(a, -1.0, 1.0)),
    'ARCTANGENT':     lambda a, b, c: dr.atan(a),
    'ARCTAN2':        lambda a, b, c: dr.atan2(a, b),
    'SINH':           lambda a, b, c: dr.sinh(a),
    'COSH':           lambda a, b, c: dr.cosh(a),
    'TANH':           lambda a, b, c: dr.tanh(a),
    'RADIANS':        lambda a, b, c: a * (dr.pi / 180.0),
    'DEGREES':        lambda a, b, c: a * (180.0 / dr.pi),
}


def register(mi, dr):
    '''
    Define and register the plugin for the active variant

    mi.Texture is a different class per variant, so a class defined at
    module scope would bind to whichever variant was active on first
    import and never rebind. Defining it inside this factory means
    register_plugins() can be called again after every set_variant.
    The class body should not be moved out of this function.
    '''


    class Math(mi.Texture):
        '''
        This plugin provides a simple math texture with a total of
        41 operations. Operations are done safely in order to prevent
        NaNs (e.g. division by 0 are replaced by 0.0)

        '''
        def __init__(self, props: mi.Properties) -> None:
            super().__init__(props)

            self.a : mi.Texture = get_texture(props, 'a', 0.0)
            self.b : mi.Texture = get_texture(props, 'b', 0.0)
            self.c : mi.Texture = get_texture(props, 'c', 0.0)
            self.use_clamp : bool = props.get('use_clamp', False)

            self.op : str = props.get('op')

        def _process(self, a, b, c):
            result = _MATH_OPS[self.op](a, b, c)
            if self.use_clamp:
                return dr.clip(result, 0.0, 1.0)

            return result


        def eval(self, si: mi.SurfaceInteraction3f, active=True) -> mi.UnpolarizedSpectrum:
            return mi.UnpolarizedSpectrum(self._process(self.a.eval(si, active),
                                                         self.b.eval(si, active),
                                                         self.c.eval(si, active)))

        def eval_1(self, si: mi.SurfaceInteraction3f, active=True) -> mi.Float:
            return mi.Float(self._process(self.a.eval_1(si, active),
                                          self.b.eval_1(si, active),
                                          self.c.eval_1(si, active)))


        def eval_3(self, si: mi.SurfaceInteraction3f, active=True) -> mi.Color3f:
            return mi.Color3f(self._process(self.a.eval_3(si, active),
                                            self.b.eval_3(si, active),
                                            self.c.eval_3(si, active)))

        def mean(self):
            return 0.5

        def traverse(self, cb: mi.TraversalCallback) -> None:
            cb.put('a', self.a, mi.ParamFlags.Differentiable)
            cb.put('b', self.b, mi.ParamFlags.Differentiable)
            cb.put('c', self.c, mi.ParamFlags.Differentiable)

        def parameters_changed(self, keys=None) -> None:
            pass

        def is_spatially_varying(self):
            return (self.a.is_spatially_varying() or
                    self.b.is_spatially_varying() or
                    self.c.is_spatially_varying())

        def to_string(self):
            return (f'Math[op={self.op}, use_clamp={self.use_clamp},\n'
                    f'a = {self.a}\n b = {self.b}\n c = {self.c}]\n')

    mi.register_texture('math', Math)
