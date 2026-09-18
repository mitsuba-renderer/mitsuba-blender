'''A BSDF that shadow rays ignore.

Cycles objects can be hidden from shadow rays alone (``visible_shadow``
off): camera rays and BSDF-sampled bounce rays hit the object as usual,
while next-event estimation towards lights, the sun and the world passes
through it. Mitsuba's per-shape ``visibility`` classes cannot express
that, but its null machinery can. A shape whose BSDF carries the
``BSDFFlags.Null`` flag is left out of occlusion queries
(``Scene.ray_test``), and ``Scene.ray_test_tr`` multiplies shadow rays by
``eval_null()`` of every such shape they cross. Path tracing, on the other
hand, treats such a hit like any other surface as long as the sampled lobe
is not the null one.

The ``shadowless`` BSDF wraps a nested ``bsdf`` and adds the null flag.
``sample``, ``eval``, ``pdf`` and the attribute queries forward to the
nested BSDF and never produce the null lobe, so camera and bounce rays
scatter exactly as the nested BSDF does, and ``eval_null`` returns full
transmittance, so shadow rays pass. The null component is the last one,
like in the ``mask`` plugin.

Integrators that walk through null surfaces along their own rays
(``Scene.ray_intersect_tr``, used by ``direct``) pass through a
``shadowless`` shape without scattering, which is not what Cycles does;
the ``path`` family only walks shadow rays.
'''


def register(mi, dr):
    '''
    Define and register the plugin for the active variant

    mi.BSDF is a different class per variant, so the class must be defined
    inside this factory, like the other plugins of this package.
    '''

    class Shadowless(mi.BSDF):
        def __init__(self, props):
            super().__init__(props)
            nested = [obj for _, obj in props.objects()
                      if isinstance(obj, mi.BSDF)]
            if len(nested) != 1:
                raise RuntimeError('shadowless: exactly one nested BSDF is '
                                   f'required, got {len(nested)}')
            self.nested = nested[0]

            components = [int(self.nested.flags(i))
                          for i in range(self.nested.component_count())]
            self.null_index = len(components)
            components.append(int(mi.BSDFFlags.Null | mi.BSDFFlags.FrontSide
                                  | mi.BSDFFlags.BackSide))
            self.m_components = components
            self.m_flags = int(self.nested.flags()) | components[-1]

        def _null_only(self, ctx):
            '''Whether the caller asked for the null component alone'''
            return ctx.component == self.null_index

        def sample(self, ctx, si, sample1, sample2, active=True):
            if self._null_only(ctx):
                return dr.zeros(mi.BSDFSample3f), mi.Spectrum(0.0)
            return self.nested.sample(ctx, si, sample1, sample2, active)

        def eval(self, ctx, si, wo, active=True):
            if self._null_only(ctx):
                return mi.Spectrum(0.0)
            return self.nested.eval(ctx, si, wo, active)

        def pdf(self, ctx, si, wo, active=True):
            if self._null_only(ctx):
                return mi.Float(0.0)
            return self.nested.pdf(ctx, si, wo, active)

        def eval_pdf(self, ctx, si, wo, active=True):
            if self._null_only(ctx):
                return mi.Spectrum(0.0), mi.Float(0.0)
            return self.nested.eval_pdf(ctx, si, wo, active)

        def eval_null(self, si, active=True):
            return mi.Spectrum(1.0)

        def eval_features(self, si, active=True):
            return self.nested.eval_features(si, active)

        def has_attribute(self, name, active=True):
            return self.nested.has_attribute(name, active)

        def eval_attribute(self, name, si, active=True):
            return self.nested.eval_attribute(name, si, active)

        def eval_attribute_1(self, name, si, active=True):
            return self.nested.eval_attribute_1(name, si, active)

        def eval_attribute_3(self, name, si, active=True):
            return self.nested.eval_attribute_3(name, si, active)

        def traverse(self, cb):
            cb.put('nested_bsdf', self.nested, mi.ParamFlags.Differentiable)

        def parameters_changed(self, keys=None):
            pass

        def to_string(self):
            return f'Shadowless[\n  nested_bsdf = {self.nested}\n]'

    mi.register_bsdf('shadowless', Shadowless)
