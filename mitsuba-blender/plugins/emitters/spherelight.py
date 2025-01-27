from __future__ import annotations # Delayed parsing of type annotations

from typing import Tuple, List

import drjit as dr
import mitsuba as mi

class SphereLight(mi.Emitter):
    '''
    A sphere light source, similar to the one implemented in Cycles.

    Parameters:
        position: Center of the sphere (default: [0, 0, 0])
        radius: Radius of the sphere (default: 1.0)
        soft_falloff: Whether to use a soft falloff (default: True)
        intensity: Intensity of the light (default: 1.0)
    '''
    def __init__(self, props) -> None:
        super().__init__(props)
        self.m_flags = +mi.EmitterFlags.DeltaPosition
        self.m_needs_sample_3 = True

        self.position = mi.Vector3f(props.get('position', [0, 0, 0]))
        self.radius = mi.Float(props.get('radius', 1.0))
        self.soft_falloff = props.get('soft_falloff', True)
        self.intensity    = props.get('intensity', 1.0)
        if isinstance(self.intensity, float) or isinstance(self.intensity, int):
            self.intensity = mi.load_dict({ 'type': 'uniform', 'value': self.intensity }, parallel=False)

        dr.make_opaque(self.position, self.radius)

    def parameters_changed(self, keys) -> None:
        if 'position' in keys:
            dr.make_opaque(self.position)
        if 'radius' in keys:
            dr.make_opaque(self.radius)
        return super().parameters_changed(keys)

    def traverse(self, callback):
        callback.put_parameter("position",       self.position,       mi.ParamFlags.Differentiable)
        callback.put_parameter("radius",       self.radius,       mi.ParamFlags.Differentiable)
        callback.put_object("intensity",       self.intensity,    mi.ParamFlags.Differentiable)
        callback.put_parameter("soft_falloff", self.soft_falloff, mi.ParamFlags.NonDifferentiable)

    def falloff(self, p) -> mi.Float:
        if self.soft_falloff:
            return 2.0 * dr.clip((1.0 - dr.norm(self.position - p) / self.radius), 0.0, 1.0)
        else:
            return mi.Float(1.0)

    def sample_direction(self,
                         it: mi.Interaction3f,
                         sample: mi.Vector2f,
                         active: mi.Bool = True) -> Tuple[mi.DirectionSample3f, mi.Spectrum]:
        largest_uint32 = int(2**32 - 1)
        sample3 = mi.sample_tea_float32(sample[0] * largest_uint32, sample[1] * largest_uint32)

        r =  1.0 - dr.abs(mi.warp.interval_to_tent(sample3))
        r_pdf = 1.0 - r

        d = mi.warp.square_to_uniform_sphere(sample)
        p = self.radius * r * d + self.position

        ds = dr.zeros(mi.DirectionSample3f)
        ds.p       = p
        ds.n       = 0.0
        ds.uv      = 0.0
        ds.time    = it.time
        ds.pdf     = dr.detach(mi.warp.square_to_uniform_sphere_pdf(d) * r_pdf)
        ds.delta   = True
        ds.emitter = mi.EmitterPtr(self)
        ds.d       = dr.normalize(ds.p - it.p)
        ds.dist    = dr.norm(ds.p - it.p)

        si = dr.zeros(mi.SurfaceInteraction3f)
        si.wavelengths = it.wavelengths

        value = self.eval_direction(it, ds, active)
        weight = value

        return ( ds, weight )

    def pdf_direction(self,
                      it: mi.Interaction3f,
                      ds: mi.DirectionSample3f,
                      active: mi.Bool = True) -> mi.Float:
        d = dr.normalize(ds.p - self.position)
        r = dr.clip(dr.norm(ds.p - self.position), 0.0, 1.0) / self.radius
        r_pdf = 1.0 - r
        return dr.detach(mi.warp.square_to_uniform_sphere_pdf(d) * r_pdf)

    def eval_direction(self,
                       it: mi.Interaction3f,
                       ds: mi.DirectionSample3f,
                       active: mi.Bool = True) -> mi.Spectrum:
        si = dr.zeros(mi.SurfaceInteraction3f)
        si.wavelengths = it.wavelengths

        spec = self.intensity.eval(si, active) * dr.rcp(dr.squared_norm(ds.p - it.p))
        spec *= self.falloff(ds.p)

        return spec

    def eval(self,
             si: mi.SurfaceInteraction3f,
             active: mi.Bool = True) -> mi.Spectrum:
        return 0.0

    def sample_ray(self,
                   time: mi.Float,
                   sample1: mi.Float,
                   sample2: mi.Point2f,
                   active: mi.Bool = True) -> Tuple[mi.Ray3f, mi.Color3f]:
        raise NotImplementedError('SphereLight.sample_ray')

    def sample_wavelengths(self,
                           si: mi.SurfaceInteraction3f,
                           sample: mi.Float,
                           active: mi.Bool = True) -> Tuple[mi.Wavelength, mi.Spectrum]:
        raise NotImplementedError('SphereLight.sample_wavelengths')

    def pdf_wavelengths(self,
                        wavelengths: mi.Spectrum,
                        active: mi.Bool = True) -> mi.Spectrum:
        raise NotImplementedError('SphereLight.pdf_wavelengths')

    def bbox(self):
        return mi.ScalarBoundingBox3f(
            self.position - self.radius,
            self.position + self.radius
        )

    def __repr__(self) -> str:
        return f'SphereLight[position={self.position}, radius={self.radius}, intensity={self.intensity}]'

mi.register_emitter('spherelight', SphereLight)
