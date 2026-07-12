import ast

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import PropertyGroup


class MitsubaPluginProps:
    '''Mixin for property groups that map directly to a Mitsuba plugin.'''
    plugin_type = None

    @classmethod
    def prop_names(cls):
        return tuple(cls.__dict__.get('__annotations__', ()))

    def draw(self, layout):
        for name in self.prop_names():
            layout.prop(self, name)

    def to_dict(self):
        params = {'type': self.plugin_type}
        for name in self.prop_names():
            params[name] = getattr(self, name)
        return params


###################
##  Integrators  ##
###################

class MitsubaPathProps(MitsubaPluginProps, PropertyGroup):
    plugin_type = 'path'
    max_depth: IntProperty(
        name='Max Depth',
        description='Longest path depth (-1 = infinite)',
        default=-1, soft_min=-1)
    rr_depth: IntProperty(
        name='Russian Roulette Depth',
        description='Minimum path depth at which russian roulette is used',
        default=5, soft_min=0)
    hide_emitters: BoolProperty(
        name='Hide Emitters',
        description='Hide directly visible emitters',
        default=False)


class MitsubaDirectProps(MitsubaPluginProps, PropertyGroup):
    plugin_type = 'direct'
    emitter_samples: IntProperty(
        name='Emitter Samples',
        description='Number of samples generated with the direct illumination strategy',
        default=1, soft_min=1)
    bsdf_samples: IntProperty(
        name='BSDF Samples',
        description='Number of samples generated with the BSDF sampling strategy',
        default=1, soft_min=1)
    hide_emitters: BoolProperty(
        name='Hide Emitters',
        description='Hide directly visible emitters',
        default=False)


class MitsubaVolPathProps(MitsubaPluginProps, PropertyGroup):
    plugin_type = 'volpath'
    max_depth: IntProperty(
        name='Max Depth',
        description='Longest path depth (-1 = infinite)',
        default=-1, soft_min=-1)
    rr_depth: IntProperty(
        name='Russian Roulette Depth',
        description='Minimum path depth at which russian roulette is used',
        default=5, soft_min=0)
    hide_emitters: BoolProperty(
        name='Hide Emitters',
        description='Hide directly visible emitters',
        default=False)


class MitsubaVolPathMisProps(MitsubaPluginProps, PropertyGroup):
    plugin_type = 'volpathmis'
    max_depth: IntProperty(
        name='Max Depth',
        description='Longest path depth (-1 = infinite)',
        default=-1, soft_min=-1)
    rr_depth: IntProperty(
        name='Russian Roulette Depth',
        description='Minimum path depth at which russian roulette is used',
        default=5, soft_min=0)
    hide_emitters: BoolProperty(
        name='Hide Emitters',
        description='Hide directly visible emitters',
        default=False)


class MitsubaPtracerProps(MitsubaPluginProps, PropertyGroup):
    plugin_type = 'ptracer'
    max_depth: IntProperty(
        name='Max Depth',
        description='Longest path depth (-1 = infinite)',
        default=-1, soft_min=-1)
    rr_depth: IntProperty(
        name='Russian Roulette Depth',
        description='Minimum path depth at which russian roulette is used',
        default=5, soft_min=0)
    hide_emitters: BoolProperty(
        name='Hide Emitters',
        description='Hide directly visible emitters',
        default=False)


# AOV variables selectable in the UI. The output name doubles as the type.
AOV_NAMES = ('albedo', 'depth', 'position', 'uv', 'geo_normal', 'sh_normal',
             'dp_du', 'dp_dv', 'duv_dx', 'duv_dy')

NESTED_INTEGRATOR_ITEMS = [
    ('path', 'Path Tracer', 'Standard path tracer'),
    ('direct', 'Direct Illumination', 'Direct illumination integrator'),
    ('volpath', 'Volumetric Path Tracer', 'Volumetric path tracer'),
    ('volpathmis', 'Volumetric Path Tracer (MIS)',
     'Volumetric path tracer with spectral MIS'),
    ('ptracer', 'Particle Tracer', 'Particle tracer starting from the emitters'),
]


class MitsubaAovProps(MitsubaPluginProps, PropertyGroup):
    plugin_type = 'aov'
    albedo: BoolProperty(name='Albedo', default=False)
    depth: BoolProperty(name='Depth', default=False)
    position: BoolProperty(name='Position', default=False)
    uv: BoolProperty(name='UV Coordinates', default=False)
    geo_normal: BoolProperty(name='Geometric Normals', default=False)
    sh_normal: BoolProperty(name='Shading Normals', default=False)
    dp_du: BoolProperty(name='Position Partial Derivative w.r.t. U', default=False)
    dp_dv: BoolProperty(name='Position Partial Derivative w.r.t. V', default=False)
    duv_dx: BoolProperty(name='UV Partial Derivative w.r.t. X', default=False)
    duv_dy: BoolProperty(name='UV Partial Derivative w.r.t. Y', default=False)
    nested_integrator: EnumProperty(
        name='Image Integrator',
        description='Integrator used to render the image alongside the AOVs',
        items=NESTED_INTEGRATOR_ITEMS,
        default='path')
    path: PointerProperty(type=MitsubaPathProps)
    direct: PointerProperty(type=MitsubaDirectProps)
    volpath: PointerProperty(type=MitsubaVolPathProps)
    volpathmis: PointerProperty(type=MitsubaVolPathMisProps)
    ptracer: PointerProperty(type=MitsubaPtracerProps)

    def draw(self, layout):
        col = layout.column(heading='Variables')
        for name in AOV_NAMES:
            col.prop(self, name)
        layout.prop(self, 'nested_integrator')
        getattr(self, self.nested_integrator).draw(layout.box())

    def to_dict(self):
        aovs = ['%s:%s' % (name, name) for name in AOV_NAMES
                if getattr(self, name)]
        return {
            'type': 'aov',
            'aovs': ','.join(aovs),
            self.nested_integrator: getattr(self, self.nested_integrator).to_dict(),
        }


class MitsubaAvailableIntegrators(PropertyGroup):
    path: PointerProperty(type=MitsubaPathProps)
    direct: PointerProperty(type=MitsubaDirectProps)
    volpath: PointerProperty(type=MitsubaVolPathProps)
    volpathmis: PointerProperty(type=MitsubaVolPathMisProps)
    aov: PointerProperty(type=MitsubaAovProps)
    ptracer: PointerProperty(type=MitsubaPtracerProps)


################
##  Samplers  ##
################

class MitsubaIndependentProps(MitsubaPluginProps, PropertyGroup):
    plugin_type = 'independent'
    sample_count: IntProperty(
        name='Sample Count',
        description='Number of samples per pixel',
        default=4, soft_min=1)
    seed: IntProperty(name='Seed', description='Seed offset', default=0)


class MitsubaStratifiedProps(MitsubaPluginProps, PropertyGroup):
    plugin_type = 'stratified'
    sample_count: IntProperty(
        name='Sample Count',
        description='Number of samples per pixel',
        default=4, soft_min=1)
    seed: IntProperty(name='Seed', description='Seed offset', default=0)
    jitter: BoolProperty(
        name='Jitter',
        description='Additional random jitter within the stratum',
        default=True)


class MitsubaMultijitterProps(MitsubaPluginProps, PropertyGroup):
    plugin_type = 'multijitter'
    sample_count: IntProperty(
        name='Sample Count',
        description='Number of samples per pixel',
        default=4, soft_min=1)
    seed: IntProperty(name='Seed', description='Seed offset', default=0)
    jitter: BoolProperty(
        name='Jitter',
        description='Additional random jitter within the substratum',
        default=True)


class MitsubaOrthogonalProps(MitsubaPluginProps, PropertyGroup):
    plugin_type = 'orthogonal'
    sample_count: IntProperty(
        name='Sample Count',
        description='Number of samples per pixel',
        default=4, soft_min=1)
    seed: IntProperty(name='Seed', description='Seed offset', default=0)
    strength: IntProperty(
        name='Strength',
        description='Strength of the orthogonal array',
        default=2, soft_min=2)
    jitter: BoolProperty(
        name='Jitter',
        description='Additional random jitter within the substratum',
        default=True)


class MitsubaLdsamplerProps(MitsubaPluginProps, PropertyGroup):
    plugin_type = 'ldsampler'
    sample_count: IntProperty(
        name='Sample Count',
        description='Number of samples per pixel',
        default=4, soft_min=1)
    seed: IntProperty(name='Seed', description='Seed offset', default=0)


class MitsubaAvailableSamplers(PropertyGroup):
    independent: PointerProperty(type=MitsubaIndependentProps)
    stratified: PointerProperty(type=MitsubaStratifiedProps)
    multijitter: PointerProperty(type=MitsubaMultijitterProps)
    orthogonal: PointerProperty(type=MitsubaOrthogonalProps)
    ldsampler: PointerProperty(type=MitsubaLdsamplerProps)


##############################
##  Reconstruction filters  ##
##############################

class MitsubaBoxProps(MitsubaPluginProps, PropertyGroup):
    plugin_type = 'box'


class MitsubaTentProps(MitsubaPluginProps, PropertyGroup):
    plugin_type = 'tent'


class MitsubaGaussianProps(MitsubaPluginProps, PropertyGroup):
    plugin_type = 'gaussian'
    stddev: FloatProperty(
        name='Standard Deviation',
        description='Standard deviation of the gaussian',
        default=0.5, soft_min=0.0)


class MitsubaMitchellProps(MitsubaPluginProps, PropertyGroup):
    plugin_type = 'mitchell'
    B: FloatProperty(
        name='B',
        description='B parameter from the original paper',
        default=1.0 / 3.0)
    C: FloatProperty(
        name='C',
        description='C parameter from the original paper',
        default=1.0 / 3.0)


class MitsubaCatmullromProps(MitsubaPluginProps, PropertyGroup):
    plugin_type = 'catmullrom'


class MitsubaLanczosProps(MitsubaPluginProps, PropertyGroup):
    plugin_type = 'lanczos'
    lobes: IntProperty(
        name='Lobes',
        description='Number of filter side-lobes',
        default=3, soft_min=1)


class MitsubaAvailableRfilters(PropertyGroup):
    box: PointerProperty(type=MitsubaBoxProps)
    tent: PointerProperty(type=MitsubaTentProps)
    gaussian: PointerProperty(type=MitsubaGaussianProps)
    mitchell: PointerProperty(type=MitsubaMitchellProps)
    catmullrom: PointerProperty(type=MitsubaCatmullromProps)
    lanczos: PointerProperty(type=MitsubaLanczosProps)


########################
##  Top-level groups  ##
########################

def _variant_items():
    import mitsuba
    return [(v, v, '') for v in mitsuba.variants()]


def _default_variant():
    import mitsuba
    variants = mitsuba.variants()
    return 'scalar_rgb' if 'scalar_rgb' in variants else variants[0]


INTEGRATOR_ITEMS = [
    ('path', 'Path Tracer', 'Standard path tracer'),
    ('direct', 'Direct Illumination', 'Direct illumination integrator with MIS'),
    ('volpath', 'Volumetric Path Tracer', 'Volumetric path tracer'),
    ('volpathmis', 'Volumetric Path Tracer (MIS)',
     'Volumetric path tracer with spectral MIS'),
    ('aov', 'AOVs', 'Arbitrary output variables describing the visible surfaces'),
    ('ptracer', 'Particle Tracer', 'Particle tracer starting from the emitters'),
]

SAMPLER_ITEMS = [
    ('independent', 'Independent', 'Independent uniformly distributed samples'),
    ('stratified', 'Stratified', 'Stratified samples'),
    ('multijitter', 'Multijitter', 'Correlated multi-jittered samples'),
    ('orthogonal', 'Orthogonal Array', 'Orthogonal array samples'),
    ('ldsampler', 'Low Discrepancy', 'Low discrepancy samples'),
]

RFILTER_ITEMS = [
    ('box', 'Box', 'Box filter'),
    ('tent', 'Tent', 'Triangular filter'),
    ('gaussian', 'Gaussian', 'Windowed gaussian filter'),
    ('mitchell', 'Mitchell', 'Mitchell-Netravali cubic spline filter'),
    ('catmullrom', 'Catmull-Rom', 'Catmull-Rom spline filter'),
    ('lanczos', 'Lanczos', 'Windowed lanczos sinc filter'),
]


class MitsubaRenderSettings(PropertyGroup):
    variant: EnumProperty(
        name='Variant',
        items=_variant_items(),
        default=_default_variant())

    active_integrator: EnumProperty(
        name='Integrator',
        items=INTEGRATOR_ITEMS,
        default='path')

    available_integrators: PointerProperty(type=MitsubaAvailableIntegrators)

    custom_integrator: StringProperty(
        name='Custom Integrator (dict)',
        description='Python dict literal used verbatim as the integrator, '
                    "e.g. {'type': 'stokes', 'nested': {'type': 'path'}}. "
                    'Overrides the integrator selection above when non-empty',
        default='')

    def integrator_to_dict(self):
        custom = self.custom_integrator.strip()
        if custom:
            integrator = ast.literal_eval(custom)
            if not isinstance(integrator, dict):
                raise ValueError('The custom integrator must be a Python dict literal, '
                                 f'got: {self.custom_integrator!r}')
            return integrator
        return getattr(self.available_integrators, self.active_integrator).to_dict()

    @classmethod
    def register(cls):
        bpy.types.Scene.mitsuba = PointerProperty(
            name='Mitsuba Render Settings',
            description='Mitsuba render settings',
            type=cls,
        )

    @classmethod
    def unregister(cls):
        del bpy.types.Scene.mitsuba


class MitsubaCameraSettings(PropertyGroup):
    active_sampler: EnumProperty(
        name='Sampler',
        items=SAMPLER_ITEMS,
        default='independent')

    samplers: PointerProperty(type=MitsubaAvailableSamplers)

    active_rfilter: EnumProperty(
        name='Reconstruction Filter',
        items=RFILTER_ITEMS,
        default='box')

    rfilters: PointerProperty(type=MitsubaAvailableRfilters)

    def sampler_to_dict(self):
        return getattr(self.samplers, self.active_sampler).to_dict()

    def rfilter_to_dict(self):
        return getattr(self.rfilters, self.active_rfilter).to_dict()

    @classmethod
    def register(cls):
        bpy.types.Camera.mitsuba = PointerProperty(
            name='Mitsuba Camera Settings',
            description='Mitsuba camera settings',
            type=cls,
        )

    @classmethod
    def unregister(cls):
        del bpy.types.Camera.mitsuba


classes = (
    MitsubaPathProps,
    MitsubaDirectProps,
    MitsubaVolPathProps,
    MitsubaVolPathMisProps,
    MitsubaPtracerProps,
    MitsubaAovProps,
    MitsubaAvailableIntegrators,
    MitsubaIndependentProps,
    MitsubaStratifiedProps,
    MitsubaMultijitterProps,
    MitsubaOrthogonalProps,
    MitsubaLdsamplerProps,
    MitsubaAvailableSamplers,
    MitsubaBoxProps,
    MitsubaTentProps,
    MitsubaGaussianProps,
    MitsubaMitchellProps,
    MitsubaCatmullromProps,
    MitsubaLanczosProps,
    MitsubaAvailableRfilters,
    MitsubaRenderSettings,
    MitsubaCameraSettings,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
