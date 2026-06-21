from __future__ import annotations  # Delayed parsing of type annotations

import drjit as dr
import mitsuba as mi

class TranslucentBSDF(mi.BSDF):
    """
    Translucent BSDF (Lambertian diffuse transmission) that matches Blender Cycles 4.5 Translucent shader node.

    Attributes
    ----------
    color : mi.Texture or mi.Color3f
        Underlying texture or color of the BSDF, default is white (mi.Color3f(1)).

    TODO Support for normal maps
    """

    def __init__(self, props):
        mi.BSDF.__init__(self, props)

        self.color = props.get_texture("color", 1.0)

        self.m_flags = mi.BSDFFlags.DiffuseTransmission | mi.BSDFFlags.FrontSide | mi.BSDFFlags.BackSide
        self.m_components = [self.m_flags]

    def eval(self, ctx, si, wo, active):
        active &= mi.Frame3f.cos_theta(si.wi) * mi.Frame3f.cos_theta(wo) >= mi.Float(0.0)
        coso = dr.abs(mi.Frame3f.cos_theta(wo))
        color = self.color.eval(si, active) 
        return dr.select(active, mi.Color3f(0.0), color * dr.inv_pi * coso)

    def pdf(self, ctx, si, wo, active):
        active &= mi.Frame3f.cos_theta(si.wi) * mi.Frame3f.cos_theta(wo) >= mi.Float(0.0)
        coso = dr.abs(mi.Frame3f.cos_theta(wo))
        return dr.select(active, 0.0, coso * dr.inv_pi)
    
    def sample(self, ctx, si, sample1, sample2, active = True):        
        bs = mi.BSDFSample3f()
        bs.wo = mi.warp.square_to_cosine_hemisphere(sample2)
        bs.wo.z = dr.select(mi.Frame3f.cos_theta(si.wi) > mi.Float(0.0), -bs.wo.z, bs.wo.z)
        bs.pdf = self.pdf(ctx, si, bs.wo, active)
        bs.eta = mi.Float(1.0)
        bs.sampled_component = self.m_components[0]
        bs.sampled_type = +mi.BSDFFlags.DiffuseTransmission

        return bs, self.color.eval(si, active)
    
    def traverse(self, cb):
        cb.put('color', self.color, mi.ParamFlags.Differentiable)

    def parameters_changed(self, keys):
        print("🏝️ there is nothing to do here 🏝️")

mi.register_bsdf("translucent", lambda props: TranslucentBSDF(props))