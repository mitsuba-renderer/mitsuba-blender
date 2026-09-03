from __future__ import annotations

from typing import TYPE_CHECKING
import drjit as dr
import mitsuba as mi

from .common import get_vector_texture

if TYPE_CHECKING:
    import mitsuba as mi
    import drjit as dr



##################
##  Arithmetic  ##
##################

def _safe_divide(a, b):
    ok = b != 0.0
    return dr.select(ok, a / dr.select(ok, b, 1.0), 0.0)

def _normalize(a):
    n = dr.norm(a)
    ok = n > 0.0
    return dr.select(ok, a / dr.select(ok, n, 1.0), mi.Color3f(0.0))

def _fract(a):
    return a - dr.floor(a)

def _modulo(a, b):
    return _safe_divide(a, b) * 0.0 + dr.select(b != 0.0,
        a - dr.trunc(a / dr.select(b != 0.0, b, 1.0)) * b, 0.0)


_VECTOR_OPS = {
    'ADD': lambda a, b, c, s: a + b,
    'SUBTRACT': lambda a, b, c, s: a - b,
    'MULTIPLY': lambda a, b, c, s: a * b,
    'DIVIDE': lambda a, b, c, s: _safe_divide(a, b),
    'MULTIPLY_ADD': lambda a, b, c, s: a * b + c,
    'CROSS_PRODUCT': lambda a, b, c, s: dr.cross(a, b),
    'DOT_PRODUCT': lambda a, b, c, s: dr.dot(a, b),
    'DISTANCE': lambda a, b, c, s: dr.norm(a - b),
    'LENGTH': lambda a, b, c, s: dr.norm(a),
    'SCALE': lambda a, b, c, s: a * s,
    'NORMALIZE': lambda a, b, c, s: _normalize(a),
    'ABSOLUTE': lambda a, b, c, s: dr.abs(a),
    'MINIMUM': lambda a, b, c, s: dr.minimum(a, b),
    'MAXIMUM': lambda a, b, c, s: dr.maximum(a, b),
    'FLOOR': lambda a, b, c, s: dr.floor(a),
    'CEIL': lambda a, b, c, s: dr.ceil(a),
    'FRACTION': lambda a, b, c, s: _fract(a),
    'MODULO': lambda a, b, c, s: _modulo(a, b),
    'SINE': lambda a, b, c, s: dr.sin(a),
    'COSINE': lambda a, b, c, s: dr.cos(a),
    'TANGENT': lambda a, b, c, s: dr.tan(a)
}

_SCALAR_OPS = {'DOT_PRODUCT', 'DISTANCE', 'LENGTH'}

def register(mi, dr):
    '''
    Define and register the plugin for the active variant

    mi.Texture is a different class per variant, so a class defined at
    module scope would bind to whichever variant was active on first
    import and never rebind. Defining it inside this factory means
    register_plugins() can be called again after every set_variant.
    The class body should not be moved out of this function.
    '''

    class VectMath(mi.Texture):
        ''' Math operation on vector

            Equivalent to the Math texture but applied on vector, hence
            new operations such as dot product, normalize, cross product,
            etc. can be used on the inputs.
        '''
        def __init__(self, props: mi.Properties):
            super().__init__(props)

            self.vec_0 = get_vector_texture(props, 'vec_0', 0.0)
            self.vec_1 = get_vector_texture(props, 'vec_1', 0.0)
            self.vec_2 = get_vector_texture(props, 'vec_2', 0.0)
            self.scale = get_vector_texture(props, 'scale', 1.0)

            self.op_fn = props.get('op')
            if self.op_fn is None:
                raise RuntimeError('vect_math plugin require an "op" parameter')


        def _process(self, si, active):
            return _VECTOR_OPS[self.op_fn](self.vec_0.eval_3(si, active),
                                           self.vec_1.eval_3(si, active),
                                           self.vec_2.eval_3(si, active),
                                           self.scale.eval_1(si, active))


        def eval(self, si, active=True):
            return mi.UnpolarizedSpectrum(self.eval_3(si, active))

        def eval_1(self, si, active=True):
            result = self._process(si, active)
            if self.op_fn in _SCALAR_OPS:
                return result
            return (result.x + result.y + result.z) * (1.0 / 3.0)

        def eval_3(self, si, active=True):
            result = self._process(si, active)
            if self.op_fn in _SCALAR_OPS:
                return mi.Color3f(result, result, result)

            return result

        def mean(self):
            return 0.5

        def traverse(self, cb: mi.TraversalCallback):
            cb.put('vec_0', self.vec_0, mi.ParamFlags.Differentiable)
            cb.put('vec_1', self.vec_1, mi.ParamFlags.Differentiable)
            cb.put('vec_2', self.vec_2, mi.ParamFlags.Differentiable)
            cb.put('scale', self.scale, mi.ParamFlags.Differentiable)

        def parameters_changed(self, keys=None):
            pass

        def is_spatially_varying(self):
            return (self.vec_0.is_spatially_varying() or
                    self.vec_1.is_spatially_varying() or
                    self.vec_2.is_spatially_varying() or
                    self.scale.is_spatially_varying())

        def to_string(self):
            return (f'VectMath[ op = {self.op_fn},\n'
                    f'vec_0 = {self.vec_0},\n'
                    f'vec_1 = {self.vec_1},\n'
                    f'vec_2 = {self.vec_2},\n'
                    f'scale = {self.scale}\n]')




    mi.register_texture('vect_math', VectMath)

