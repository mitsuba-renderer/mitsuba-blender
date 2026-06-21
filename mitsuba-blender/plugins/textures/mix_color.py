from __future__ import annotations # Delayed parsing of type annotations

import drjit as dr
import mitsuba as mi

blend_type_mix = 'MIX'
blend_type_mul = 'MULTIPLY'
blend_type_screen = 'SCREEN'
blend_type_overlay = 'OVERLAY'

class Mix(mi.Texture):
    '''
    Mix texture mixes colors inputs using a factor to control the amount of interpolation. Match Blender Cycles 4.5 Mix Color node.

    Attributes
    ----------
    blend_type : str
        The method used to blend the two inputs togethers. 
        Currently supported blending mode are 'MIX', 'MULTIPLY', 'SCREEN' and 'OVERLAY'. Default is 'MIX'.
    
    clamp_result : mi.Bool
        Limit the factor value between 0.0 and 1.0. Default is False.
    
    clamp_factor : mi.Bool
        Limit the Result to the range between 0.0 and 1.0. Default is False.

    factor : mi.Texture or mi.Float
        Controls the amount of mixing between the A and B inputs. Default is 0.5.

    a : mi.Texture or mi.Color3f
        First input to mix
    
    b : mi.Texture or mi.Color3f
        Second input to mix

    TODO add support for missing blend types
    '''
    def __init__(self, props):
        super().__init__(props)
        self.blend_type = props.get('blend_type', blend_type_mix)
        self.clamp_result = props.get('clamp_result', False)
        self.clamp_factor = props.get('clamp_factor', False)
        self.factor = props.get_texture('factor', 0.5)
        self.a = props.get_texture('a')
        self.b = props.get_texture('b')
    
    def parameters_changed(self, keys = ...):
        pass

    def traverse(self, cb):
        cb.put('a', self.a, +mi.ParamFlags.Differentiable)
        cb.put('b', self.b, +mi.ParamFlags.Differentiable)

    def eval(self, si, active):
        val_a = self.a.eval(si, active)
        val_b = self.b.eval(si, active)
        return mi.UnpolarizedSpectrum(self.process(si, val_a, val_b, active))

    def eval_1(self, si, active):
        val_a = self.a.eval_1(si, active)
        val_b = self.b.eval_1(si, active)
        return mi.Float(self.process(si, val_a, val_b, active))

    def eval_3(self, si, active):
        val_a = self.a.eval_3(si, active)
        val_b = self.b.eval_3(si, active)
        return mi.Color3f(self.process(si, val_a, val_b, active))

    def process(self, si, val_a, val_b, active):
        fac = self.factor.eval_1(si, active)
        if self.clamp_factor:
            fac = dr.clip(fac, 0.0, 1.0)

        result = self.blend(self.blend_type, val_a, val_b, fac)

        if self.clamp_result:
            result = dr.clip(result, 0.0, 1.0)
        
        return result
    
    def blend(self, mode, a, b, fac):
        if mode == blend_type_mix:
            res = (1 - fac) * a + fac * b
        elif mode == blend_type_screen:
            fac_inv = mi.Float(1) - fac
            res = mi.Color3f(1) - (mi.Color3f(fac_inv) + fac * (mi.Color3f(1) - b)) * (mi.Color3f(1) - a)
        elif mode == blend_type_mul:
            res = dr.minimum(a * ((mi.Color3f(1) - fac) + fac * b), mi.Color3f(1))
        elif mode == blend_type_overlay:
            fac_inv = mi.Float(1) - fac
            res = mi.Color3f(0)

            blend_mul = lambda ca, cb: ca * (fac_inv + mi.Float(2) * fac * cb)
            blend_scr = lambda ca, cb: mi.Float(1) - (fac_inv + mi.Float(2) * fac * (mi.Float(1) - cb)) * (mi.Float(1) - ca) 
            res.x = dr.select(a.x < mi.Float(0.5), blend_mul(a.x, b.x), blend_scr(a.x, b.x))
            res.y = dr.select(a.y < mi.Float(0.5), blend_mul(a.y, b.y), blend_scr(a.y, b.y))
            res.z = dr.select(a.z < mi.Float(0.5), blend_mul(a.z, b.z), blend_scr(a.z, b.z))
        else:
            raise NotImplementedError(f"Current implementation of Mix color texture does not support {mode}")
        return res
        
    def resolution(self):
        return self.a.resolution()
    
    def mean(self):
        return (self.a.mean() + self.b.mean()) / 2
    
    def is_spatially_varying(self):
        return self.a.is_spatially_varying() or self.b.is_spatially_varying()

    def to_string(self):
        return f'Mix[blend type={self.blend_type},factor={self.factor},a={self.a},b={self.b}]' 

mi.register_texture('mix_color', lambda props: Mix(props))
