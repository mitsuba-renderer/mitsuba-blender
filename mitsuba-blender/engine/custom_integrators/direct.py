import mitsuba as mi
from mitsuba import SamplingIntegrator

class MyDirectIntegrator(SamplingIntegrator):
    def __init__(self, props):
        SamplingIntegrator.__init__(self, props)

    def sample(self, scene, sampler, ray, medium, active):
        result, is_valid, depth = self.integrator_sample(scene, sampler, ray, medium, active)
        return result, is_valid, [depth]

    def integrator_sample(self, scene, sampler, rays, medium, active=True):
        import drjit as dr
        si = scene.ray_intersect(rays)
        active = si.is_valid() & active

        # Visible emitters
        emitter_vis = si.emitter(scene, active)
        result = dr.select(active, \
            emitter_vis.eval(si, active), Vector3f(0.0))
        
        ctx = mi.BSDFContext()
        bsdf = si.bsdf(rays)
        
        # Emitter sampling
        sample_emitter = active & has_flag(bsdf.flags(), BSDFFlags.Smooth)
        ds, emitter_val = scene.sample_emitter_direction(si, sampler.next_2d(sample_emitter), True, sample_emitter)
        active_e = sample_emitter & dr.neq(ds.pdf, 0.0)
        wo = si.to_local(ds.d)
        bsdf_val = bsdf.eval(ctx, si, wo, active_e)
        bsdf_pdf = bsdf.pdf(ctx, si, wo, active_e)
        mis = dr.select(ds.delta, Float(1), self.mis_weight(ds.pdf, bsdf_pdf))
        result += dr.select(active_e, emitter_val * bsdf_val * mis, Vector3f(0))

        # BSDF sampling
        active_b = active
        bs, bsdf_val = bsdf.sample(ctx, si, sampler.next_1d(active), sampler.next_2d(active), active_b)
        si_bsdf = scene.ray_intersect(si.spawn_ray(si.to_world(bs.wo)), active_b)
        emitter = si_bsdf.emitter(scene, active_b)
        active_b &= dr.neq(emitter, None)
        emitter_val = emitter.eval(si_bsdf, active_b)
        delta = has_flag(bs.sampled_type, BSDFFlags.Delta)
        ds = mi.DirectionSample3f(scene, si_bsdf, si)
        # ds.object = emitter
        emitter_pdf = dr.select(delta, Float(0), scene.pdf_emitter_direction(si, ds, active_b))
        result += dr.select(active_b, bsdf_val * emitter_val * self.mis_weight(bs.pdf, emitter_pdf), Vector3f(0))
        return result, si.is_valid(), dr.select(si.is_valid(), si.t, Float(0.0))

    def mis_weight(self, pdf_a, pdf_b):
        import drjit as dr
        pdf_a *= pdf_a
        pdf_b *= pdf_b
        return dr.select(pdf_a > 0.0, pdf_a / (pdf_a + pdf_b), Float(0.0))

    def aov_names(self):
        return ["depth.Y"]

    def to_string(self):
        return "MyDirectIntegrator[]"