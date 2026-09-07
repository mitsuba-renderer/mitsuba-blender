'''Bump mapping with the semantics of Blender's Bump node.

Cycles scales the height by Distance, differentiates it by finite differences
across the pixel footprint, and blends the perturbed normal with the original
one by Strength. This texture computes that normal and returns it in the
tangent space encoding of Mitsuba's ``normalmap`` BSDF, which applies it.

The finite differences step along the columns of the ray cone footprint
scaled by ``filter_width``, so that height detail smaller than a pixel does
not tilt the normal. Like Cycles, they use the footprint of the full pixel
(``si.footprint / si.footprint_scale``) rather than the narrower per-sample
footprint of jittered rendering. Interactions without a footprint use the
analytic gradient of the height texture when it provides one
(``eval_1_grad``), and otherwise finite differences with a fixed UV step of
``FALLBACK_STEP``. The texture reports itself as filtered, which asks the
scene to compute footprints.

Parameters:
  texture (texture): height field, evaluated with ``eval_1``
  scale (float): Blender's Distance, negative for inverted bumps. Default 1
  strength (float): Blender's Strength. Default 1
  filter_width (float): Blender's Filter Width. Default 1
'''


# UV step of the finite differences at interactions without a footprint,
# for height textures without an analytic gradient
FALLBACK_STEP = 1.0 / 1024.0


def register(mi, dr):
    class BlenderBumpMap(mi.Texture):
        def __init__(self, props):
            super().__init__(props)
            self.texture = props.get('texture')
            if not isinstance(self.texture, mi.Texture):
                raise Exception('blender_bumpmap: the "texture" parameter '
                                'must be a height texture')
            self.scale = mi.Float(props.get('scale', 1.0))
            self.strength = mi.Float(props.get('strength', 1.0))
            self.filter_width = mi.Float(props.get('filter_width', 1.0))
            dr.make_opaque(self.scale, self.strength, self.filter_width)

            # Only image textures provide an analytic UV gradient
            try:
                self.texture.eval_1_grad(dr.zeros(mi.SurfaceInteraction3f))
                self.analytic = True
            except Exception:
                self.analytic = False

        def gradient(self, si, active):
            fp = si.footprint
            s = self.filter_width / si.footprint_scale
            dx = mi.Vector2f(fp[0, 0], fp[1, 0]) * s
            dy = mi.Vector2f(fp[0, 1], fp[1, 1]) * s
            det = dx.x * dy.y - dx.y * dy.x
            valid = active & dr.isfinite(det) & (det != 0)
            if not self.analytic:
                dx = dr.select(valid, dx, mi.Vector2f(FALLBACK_STEP, 0.0))
                dy = dr.select(valid, dy, mi.Vector2f(0.0, FALLBACK_STEP))
                det = dr.select(valid, det, FALLBACK_STEP * FALLBACK_STEP)
                valid = active

            si_x = mi.SurfaceInteraction3f(si)
            si_y = mi.SurfaceInteraction3f(si)
            si_x.uv += dx
            si_y.uv += dy
            si_x.p += si.dp_du * dx.x + si.dp_dv * dx.y
            si_y.p += si.dp_du * dy.x + si.dp_dv * dy.y
            h_c = self.texture.eval_1(si, valid)
            h_x = self.texture.eval_1(si_x, valid) - h_c
            h_y = self.texture.eval_1(si_y, valid) - h_c

            # Solve [dx; dy] * grad = [h_x; h_y]
            inv_det = dr.rcp(det)
            fd = mi.Vector2f((dy.y * h_x - dx.y * h_y) * inv_det,
                             (dx.x * h_y - dy.x * h_x) * inv_det)

            if not self.analytic:
                return fd
            return dr.select(valid, fd, self.texture.eval_1_grad(si, active))

        def eval_3(self, si, active=True):
            grad = self.gradient(si, active) * self.scale

            n = si.sh_frame.n
            dp_du = si.dp_du + n * (grad.x - dr.dot(n, si.dp_du))
            dp_dv = si.dp_dv + n * (grad.y - dr.dot(n, si.dp_dv))
            m = dr.cross(dp_du, dp_dv)
            m = dr.select(dr.dot(si.n, m) < 0, -m, m)
            m = dr.normalize(dr.lerp(n, dr.normalize(m), self.strength))

            return mi.Color3f(si.to_local(m)) * 0.5 + 0.5

        def eval(self, si, active=True):
            return mi.UnpolarizedSpectrum(self.eval_3(si, active))

        def eval_1(self, si, active=True):
            c = self.eval_3(si, active)
            return (c.x + c.y + c.z) * (1.0 / 3.0)

        def mean(self):
            return 0.5

        def filtered(self):
            return True

        def is_spatially_varying(self):
            return True

        def traverse(self, cb):
            cb.put('texture', self.texture, mi.ParamFlags.Differentiable)
            cb.put('scale', self.scale, mi.ParamFlags.NonDifferentiable)
            cb.put('strength', self.strength, mi.ParamFlags.NonDifferentiable)
            cb.put('filter_width', self.filter_width,
                   mi.ParamFlags.NonDifferentiable)

        def parameters_changed(self, keys=None):
            pass

        def to_string(self):
            return (f'BlenderBumpMap[\n texture = {self.texture},\n'
                    f' scale = {self.scale},\n strength = {self.strength},\n'
                    f' filter_width = {self.filter_width}\n]')

    mi.register_texture('blender_bumpmap', BlenderBumpMap)
