"""Unit tests for material socket resolution and constant folding."""

import importlib
import math

import bpy
import pytest


@pytest.fixture(scope='session')
def ev(mi_addon):
    return importlib.import_module(
        f'{mi_addon}.convert.export.materials._eval')


@pytest.fixture
def tree():
    b_mat = bpy.data.materials.new('eval-test')
    b_mat.use_nodes = True
    yield b_mat.node_tree
    bpy.data.materials.remove(b_mat)


@pytest.fixture
def probe(tree):
    """An unconnected node providing a float and a color input socket."""
    return tree.nodes.new('ShaderNodeEmission')


def texture(result):
    assert result.__class__.__name__ == 'Texture', repr(result)
    return result.params


def by_id(sockets, identifier):
    return next(s for s in sockets if s.identifier == identifier)


def eval_texture(export_ctx, result, ctx):
    import mitsuba as mi, drjit as dr
    assert result.__class__.__name__ == 'Texture', repr(result)
    tex = mi.load_dict(result.params)
    si = dr.zeros(mi.SurfaceInteraction3f)
    return tex

def eval_float_texture(result):
    import mitsuba as mi, drjit as dr
    tex = mi.load_dict(texture(result))
    return tex.eval_1(dr.zeros(mi.SurfaceInteraction3f))

def fold_float(export_ctx, ev, tree, probe, out_socket):
    tree.links.new(out_socket, probe.inputs['Strength'])
    return ev.resolve(export_ctx, probe.inputs['Strength'])


def fold_color(export_ctx, ev, tree, probe, out_socket):
    tree.links.new(out_socket, probe.inputs['Color'])
    return ev.resolve(export_ctx, probe.inputs['Color'])


def constant(result):
    assert result.__class__.__name__ == 'Constant', repr(result)
    return result.value


def math_node(tree, operation, a, b=0.0, c=0.0):
    node = tree.nodes.new('ShaderNodeMath')
    node.operation = operation
    node.inputs[0].default_value = a
    node.inputs[1].default_value = b
    node.inputs[2].default_value = c
    return node


def test_unlinked_float_socket(export_ctx, ev, probe):
    probe.inputs['Strength'].default_value = 0.25
    result = ev.resolve(export_ctx, probe.inputs['Strength'])
    assert constant(result) == 0.25


def test_unlinked_color_socket(export_ctx, ev, probe):
    probe.inputs['Color'].default_value = (0.1, 0.2, 0.3, 1.0)
    value = constant(ev.resolve(export_ctx, probe.inputs['Color']))
    assert value == pytest.approx((0.1, 0.2, 0.3, 1.0))


def test_value_node(export_ctx, ev, tree, probe):
    node = tree.nodes.new('ShaderNodeValue')
    node.outputs['Value'].default_value = 2.5
    result = fold_float(export_ctx, ev, tree, probe, node.outputs['Value'])
    assert constant(result) == 2.5


def test_rgb_node_reads_output_socket(export_ctx, ev, tree, probe):
    # The color of an RGB node lives on its output socket; node.color is
    # the unrelated header color
    node = tree.nodes.new('ShaderNodeRGB')
    node.outputs['Color'].default_value = (0.8, 0.6, 0.4, 1.0)
    node.color = (0.9, 0.9, 0.9)
    value = constant(fold_color(export_ctx, ev, tree, probe, node.outputs['Color']))
    assert value == pytest.approx((0.8, 0.6, 0.4, 1.0))


@pytest.mark.parametrize('operation,a,b,c,expected', [
    ('ADD', 2.0, 3.0, 0.0, 5.0),
    ('SUBTRACT', 2.0, 3.0, 0.0, -1.0),
    ('MULTIPLY', 2.0, 3.0, 0.0, 6.0),
    ('DIVIDE', 3.0, 2.0, 0.0, 1.5),
    ('DIVIDE', 1.0, 0.0, 0.0, 0.0),
    ('MULTIPLY_ADD', 2.0, 3.0, 4.0, 10.0),
    ('POWER', 2.0, 10.0, 0.0, 1024.0),
    ('POWER', -2.0, 0.5, 0.0, 0.0),
    ('LOGARITHM', 8.0, 2.0, 0.0, 3.0),
    ('SQRT', 9.0, 0.0, 0.0, 3.0),
    ('SQRT', -1.0, 0.0, 0.0, 0.0),
    ('INVERSE_SQRT', 4.0, 0.0, 0.0, 0.5),
    ('ABSOLUTE', -3.0, 0.0, 0.0, 3.0),
    ('EXPONENT', 0.0, 0.0, 0.0, 1.0),
    ('MINIMUM', 2.0, 3.0, 0.0, 2.0),
    ('MAXIMUM', 2.0, 3.0, 0.0, 3.0),
    ('LESS_THAN', 1.0, 2.0, 0.0, 1.0),
    ('GREATER_THAN', 1.0, 2.0, 0.0, 0.0),
    ('SIGN', -5.0, 0.0, 0.0, -1.0),
    ('COMPARE', 1.0, 1.0001, 0.001, 1.0),
    ('COMPARE', 1.0, 1.1, 0.001, 0.0),
    ('ROUND', 2.5, 0.0, 0.0, 3.0),
    ('FLOOR', 2.7, 0.0, 0.0, 2.0),
    ('CEIL', 2.1, 0.0, 0.0, 3.0),
    ('TRUNC', -2.7, 0.0, 0.0, -2.0),
    ('FRACT', 2.75, 0.0, 0.0, 0.75),
    ('MODULO', 7.0, 3.0, 0.0, 1.0),
    ('FLOORED_MODULO', -7.0, 3.0, 0.0, 2.0),
    ('WRAP', 5.0, 3.0, 0.0, 2.0),
    ('SNAP', 7.3, 2.0, 0.0, 6.0),
    ('PINGPONG', 1.5, 1.0, 0.0, 0.5),
    ('SINE', math.pi / 2.0, 0.0, 0.0, 1.0),
    ('ARCSINE', 1.0, 0.0, 0.0, math.pi / 2.0),
    ('ARCSINE', 2.0, 0.0, 0.0, math.pi / 2.0),
    ('ARCTAN2', 1.0, 1.0, 0.0, math.pi / 4.0),
    ('RADIANS', 180.0, 0.0, 0.0, math.pi),
    ('DEGREES', math.pi, 0.0, 0.0, 180.0),
])

def test_math_operations(export_ctx, ev, tree, probe, operation, a, b, c, expected):
    import mitsuba as mi
    import drjit as dr
    node = math_node(tree, operation, a, b, c)
    result = fold_float(export_ctx, ev, tree,probe, node.outputs['Value'])
    tex = mi.load_dict(result.params)
    si = dr.zeros(mi.SurfaceInteraction3f)
    assert tex.eval_1(si) == pytest.approx(expected)


def test_math_use_clamp(export_ctx, ev, tree, probe):
    node = math_node(tree, 'ADD', 2.0, 3.0)
    node.use_clamp = True
    result = fold_float(export_ctx, ev, tree, probe, node.outputs['Value'])
    assert eval_float_texture(result) == 1.0


def test_math_chain(export_ctx, ev, tree, probe):
    add = math_node(tree, 'ADD', 3.0, 4.0)
    mul = math_node(tree, 'MULTIPLY', 0.0, 2.0)
    tree.links.new(add.outputs['Value'], mul.inputs[0])
    result = fold_float(export_ctx, ev, tree, probe, mul.outputs['Value'])
    assert eval_float_texture(result) == 14.0


def vector_math_node(tree, operation, a, b=(0.0, 0.0, 0.0)):
    node = tree.nodes.new('ShaderNodeVectorMath')
    node.operation = operation
    node.inputs[0].default_value = a
    node.inputs[1].default_value = b
    return node


def test_vector_math_dot_product(export_ctx, ev, tree, probe):
    node = vector_math_node(tree, 'DOT_PRODUCT', (1, 2, 3), (4, 5, 6))
    result = fold_float(export_ctx, ev, tree, probe, node.outputs['Value'])
    assert constant(result) == pytest.approx(32.0)


def test_vector_math_scale(export_ctx, ev, tree, probe):
    node = vector_math_node(tree, 'SCALE', (1, 2, 3))
    node.inputs['Scale'].default_value = 2.0
    value = constant(fold_color(export_ctx, ev, tree, probe, node.outputs['Vector']))
    assert value == pytest.approx((2.0, 4.0, 6.0, 1.0))


def test_vector_math_cross_product(export_ctx, ev, tree, probe):
    node = vector_math_node(tree, 'CROSS_PRODUCT', (1, 0, 0), (0, 1, 0))
    value = constant(fold_color(export_ctx, ev, tree, probe, node.outputs['Vector']))
    assert value == pytest.approx((0.0, 0.0, 1.0, 1.0))


def test_vector_math_normalize(export_ctx, ev, tree, probe):
    node = vector_math_node(tree, 'NORMALIZE', (3, 0, 4))
    value = constant(fold_color(export_ctx, ev, tree, probe, node.outputs['Vector']))
    assert value == pytest.approx((0.6, 0.0, 0.8, 1.0))


def mix_node(tree, data_type, factor, a, b, blend_type='MIX'):
    node = tree.nodes.new('ShaderNodeMix')
    node.data_type = data_type
    node.blend_type = blend_type
    suffix = {'FLOAT': 'Float', 'RGBA': 'Color'}[data_type]
    by_id(node.inputs, 'Factor_Float').default_value = factor
    by_id(node.inputs, f'A_{suffix}').default_value = a
    by_id(node.inputs, f'B_{suffix}').default_value = b
    return node, by_id(node.outputs, f'Result_{suffix}')


def test_mix_float(export_ctx, ev, tree, probe):
    import mitsuba as mi, drjit as dr
    node, out = mix_node(tree, 'FLOAT', 0.25, 0.0, 8.0)
    result = fold_float(export_ctx, ev, tree, probe, out)
    tex = mi.load_dict(texture(result))
    si = dr.zeros(mi.SurfaceInteraction3f)
    assert tex.eval_1(si) == pytest.approx(2.0)



def test_mix_float_clamp_factor(export_ctx, ev, tree, probe):
    node, out = mix_node(tree, 'FLOAT', 2.0, 0.0, 8.0)
    node.clamp_factor = True
    result = fold_float(export_ctx, ev, tree, probe, out)
    assert eval_float_texture(result) == pytest.approx(8.0)


def test_mix_float_unclamped_factor(export_ctx, ev, tree, probe):
    node, out = mix_node(tree, 'FLOAT', 2.0, 0.0, 8.0)
    node.clamp_factor = False
    result = fold_float(export_ctx, ev, tree, probe, out)
    assert eval_float_texture(result) == pytest.approx(16.0)


@pytest.mark.parametrize('blend_type,factor,expected', [
    ('MIX', 1.0, (0.5, 0.5, 0.25)),
    ('MIX', 0.5, (0.35, 0.45, 0.525)),
    ('MULTIPLY', 1.0, (0.1, 0.2, 0.2)),
    ('ADD', 0.5, (0.45, 0.65, 0.925)),
    ('SUBTRACT', 1.0, (-0.3, -0.1, 0.55)),
    ('DARKEN', 1.0, (0.2, 0.4, 0.25)),
    ('LIGHTEN', 1.0, (0.5, 0.5, 0.8)),
])
def test_mix_color_blend(export_ctx, ev, tree, probe, blend_type, factor, expected):
    import mitsuba as mi, drjit as dr
    a = (0.2, 0.4, 0.8, 1.0)
    b = (0.5, 0.5, 0.25, 1.0)
    node, out = mix_node(tree, 'RGBA', factor, a, b, blend_type)
    node.clamp_result = False
    result = fold_color(export_ctx, ev, tree, probe, out)
    tex = mi.load_dict(texture(result))
    si = dr.zeros(mi.SurfaceInteraction3f)
    assert list(tex.eval_3(si)) == pytest.approx(expected)

def test_mix_color_unsupported_blend(export_ctx, ev, tree, probe):
    _, out = mix_node(tree, 'RGBA', 0.5, (1, 0, 0, 1), (0, 1, 0, 1), 'BURN')
    result = fold_color(export_ctx, ev, tree, probe, out)
    assert isinstance(result, ev.Unsupported)
    assert 'BURN' in result.reason


def test_invert(export_ctx, ev, tree, probe):
    import mitsuba as mi, drjit  as dr
    node = tree.nodes.new('ShaderNodeInvert')
    node.inputs['Fac'].default_value = 0.5
    node.inputs['Color'].default_value = (0.2, 0.4, 1.0, 1.0)
    result =fold_color(export_ctx, ev, tree, probe, node.outputs['Color'])
    tex = mi.load_dict(texture(result))
    si = dr.zeros(mi.SurfaceInteraction3f)
    assert list(tex.eval_3(si)) == pytest.approx((0.5, 0.5, 0.5))


def test_gamma(export_ctx, ev, tree, probe):
    node = tree.nodes.new('ShaderNodeGamma')
    node.inputs['Color'].default_value = (0.25, 0.0, 1.0, 1.0)
    node.inputs['Gamma'].default_value = 0.5
    value = constant(fold_color(export_ctx, ev, tree, probe, node.outputs['Color']))
    assert value == pytest.approx((0.5, 0.0, 1.0, 1.0))


def test_brightness_contrast(export_ctx, ev, tree, probe):
    import mitsuba as mi, drjit as dr
    node = tree.nodes.new('ShaderNodeBrightContrast')
    node.inputs['Color'].default_value = (0.5, 0.0, 1.0, 1.0)
    node.inputs['Bright'].default_value = 0.1
    node.inputs['Contrast'].default_value = 0.2
    # gain = 1.2, offset = 0.1 - 0.1 = 0, clamped at zero from below
    result = fold_color(export_ctx, ev, tree, probe, node.outputs['Color'])
    tex = mi.load_dict(texture(result))
    si = dr.zeros(mi.SurfaceInteraction3f)
    assert list(tex.eval_3(si)) == pytest.approx((0.6, 0.0, 1.2))


def map_range_node(tree, value, interpolation='LINEAR', clamp=True,
                   from_range=(0.0, 10.0), to_range=(0.0, 1.0), steps=4.0):
    node = tree.nodes.new('ShaderNodeMapRange')
    node.interpolation_type = interpolation
    node.clamp = clamp
    by_id(node.inputs, 'Value').default_value = value
    by_id(node.inputs, 'From Min').default_value = from_range[0]
    by_id(node.inputs, 'From Max').default_value = from_range[1]
    by_id(node.inputs, 'To Min').default_value = to_range[0]
    by_id(node.inputs, 'To Max').default_value = to_range[1]
    by_id(node.inputs, 'Steps').default_value = steps
    return node


@pytest.mark.parametrize('value,interpolation,clamp,expected', [
    (5.0, 'LINEAR', True, 0.5),
    (15.0, 'LINEAR', True, 1.0),
    (15.0, 'LINEAR', False, 1.5),
    (5.0, 'SMOOTHSTEP', False, 0.5),
    (2.5, 'SMOOTHSTEP', False, 0.15625),
    (15.0, 'SMOOTHERSTEP', False, 1.0),
    (5.0, 'STEPPED', True, 0.5),
])
def test_map_range(export_ctx, ev, tree, probe, value, interpolation, clamp, expected):
    node = map_range_node(tree, value, interpolation, clamp)
    result = fold_float(export_ctx, ev, tree, probe, node.outputs['Result'])
    assert constant(result) == pytest.approx(expected)


def test_clamp_minmax(export_ctx, ev, tree, probe):
    node = tree.nodes.new('ShaderNodeClamp')
    node.inputs['Value'].default_value = 2.0
    node.inputs['Min'].default_value = 0.5
    node.inputs['Max'].default_value = 1.5
    result = fold_float(export_ctx, ev, tree, probe, node.outputs['Result'])
    assert constant(result) == 1.5


def test_clamp_range_swapped(export_ctx, ev, tree, probe):
    node = tree.nodes.new('ShaderNodeClamp')
    node.clamp_type = 'RANGE'
    node.inputs['Value'].default_value = 0.4
    node.inputs['Min'].default_value = 1.0
    node.inputs['Max'].default_value = 0.0
    result = fold_float(export_ctx, ev, tree, probe, node.outputs['Result'])
    assert constant(result) == pytest.approx(0.4)


def test_separate_combine_xyz(export_ctx, ev, tree, probe):
    comb = tree.nodes.new('ShaderNodeCombineXYZ')
    comb.inputs['X'].default_value = 1.0
    comb.inputs['Y'].default_value = 2.0
    comb.inputs['Z'].default_value = 3.0
    sep = tree.nodes.new('ShaderNodeSeparateXYZ')
    tree.links.new(comb.outputs['Vector'], sep.inputs['Vector'])
    result = fold_float(export_ctx, ev, tree, probe, sep.outputs['Y'])
    assert constant(result) == 2.0


def test_separate_color_hsv(export_ctx, ev, tree, probe):
    node = tree.nodes.new('ShaderNodeSeparateColor')
    node.mode = 'HSV'
    node.inputs['Color'].default_value = (0.5, 0.0, 0.0, 1.0)
    result = fold_float(export_ctx, ev, tree, probe, node.outputs['Green'])
    assert constant(result) == pytest.approx(1.0)  # saturation
    result = fold_float(export_ctx, ev, tree, probe, node.outputs['Blue'])
    assert constant(result) == pytest.approx(0.5)  # value


def test_combine_color_hsv(export_ctx, ev, tree, probe):
    node = tree.nodes.new('ShaderNodeCombineColor')
    node.mode = 'HSV'
    node.inputs['Red'].default_value = 0.0    # hue
    node.inputs['Green'].default_value = 1.0  # saturation
    node.inputs['Blue'].default_value = 1.0   # value
    value = constant(fold_color(export_ctx, ev, tree, probe, node.outputs['Color']))
    assert value == pytest.approx((1.0, 0.0, 0.0, 1.0))


def test_rgb_to_bw(export_ctx, ev, tree, probe):
    node = tree.nodes.new('ShaderNodeRGBToBW')
    node.inputs['Color'].default_value = (1.0, 0.0, 0.0, 1.0)
    result = fold_float(export_ctx, ev, tree, probe, node.outputs['Val'])
    assert constant(result) == pytest.approx(0.2126)


def test_float_to_color_conversion(export_ctx, ev, tree, probe):
    node = tree.nodes.new('ShaderNodeValue')
    node.outputs['Value'].default_value = 0.5
    value = constant(fold_color(export_ctx, ev, tree, probe, node.outputs['Value']))
    assert value == pytest.approx((0.5, 0.5, 0.5, 1.0))


def test_color_to_float_conversion(export_ctx, ev, tree, probe):
    node = tree.nodes.new('ShaderNodeRGB')
    node.outputs['Color'].default_value = (1.0, 0.0, 0.0, 1.0)
    result = fold_float(export_ctx, ev, tree, probe, node.outputs['Color'])
    assert constant(result) == pytest.approx(0.2126)


def test_reroute_chain(export_ctx, ev, tree, probe):
    node = tree.nodes.new('ShaderNodeValue')
    node.outputs['Value'].default_value = 4.0
    reroute_a = tree.nodes.new('NodeReroute')
    reroute_b = tree.nodes.new('NodeReroute')
    tree.links.new(node.outputs['Value'], reroute_a.inputs[0])
    tree.links.new(reroute_a.outputs[0], reroute_b.inputs[0])
    result = fold_float(export_ctx, ev, tree, probe, reroute_b.outputs[0])
    assert constant(result) == 4.0


def test_muted_node_passthrough(export_ctx, ev, tree, probe):
    node = tree.nodes.new('ShaderNodeValue')
    node.outputs['Value'].default_value = 3.0
    add = math_node(tree, 'ADD', 0.0, 100.0)
    tree.links.new(node.outputs['Value'], add.inputs[0])
    tree.links.new(add.outputs['Value'], probe.inputs['Strength'])
    add.mute = True
    # Blender computes the pass-through links of muted nodes on update
    bpy.context.view_layer.update()
    result = ev.resolve(export_ctx, probe.inputs['Strength'])
    assert constant(result) == 3.0


def test_muted_link_is_unlinked(export_ctx, ev, tree, probe):
    probe.inputs['Strength'].default_value = 0.75
    node = tree.nodes.new('ShaderNodeValue')
    node.outputs['Value'].default_value = 3.0
    link = tree.links.new(node.outputs['Value'], probe.inputs['Strength'])
    link.is_muted = True
    result = ev.resolve(export_ctx, probe.inputs['Strength'])
    assert constant(result) == 0.75


def test_unsupported_node(export_ctx, ev, tree, probe):
    node = tree.nodes.new('ShaderNodeTexNoise')
    result = fold_float(export_ctx, ev, tree, probe, node.outputs['Fac'])
    assert isinstance(result, ev.Unsupported)
    assert node.name in result.reason
    assert 'TEX_NOISE' in result.reason
    assert 'Strength' in result.reason


def test_unsupported_node_inside_fold(export_ctx, ev, tree, probe):
    noise = tree.nodes.new('ShaderNodeTexNoise')
    add = math_node(tree, 'ADD', 0.0, 1.0)
    tree.links.new(noise.outputs['Fac'], add.inputs[0])
    result = fold_float(export_ctx, ev, tree, probe, add.outputs['Value'])
    assert isinstance(result, ev.Unsupported)
    assert noise.name in result.reason


@pytest.fixture
def override_checker(ev):
    """Temporarily replaces the TEX_CHECKER converter, restoring the real
    one afterwards."""
    previous = ev._texture_converters.get('TEX_CHECKER')

    def _override(func):
        ev.texture_converter('TEX_CHECKER')(func)

    yield _override
    if previous is None:
        ev._texture_converters.pop('TEX_CHECKER', None)
    else:
        ev._texture_converters['TEX_CHECKER'] = previous


def test_texture_converter_registry(export_ctx, ev, tree, probe, override_checker):
    override_checker(lambda export_ctx, node, out_socket:
                     {'type': 'checkerboard'})

    node = tree.nodes.new('ShaderNodeTexChecker')
    result = fold_color(export_ctx, ev, tree, probe, node.outputs['Color'])
    assert isinstance(result, ev.Texture)
    assert result.params == {'type': 'checkerboard'}


def test_texture_converter_error_is_unsupported(export_ctx, ev, tree, probe,
                                                override_checker):
    def convert_checker(export_ctx, node, out_socket):
        raise ev.ConversionError('checker says no')
    override_checker(convert_checker)

    node = tree.nodes.new('ShaderNodeTexChecker')
    result = fold_color(export_ctx, ev, tree, probe, node.outputs['Color'])
    assert isinstance(result, ev.Unsupported)
    assert result.reason == 'checker says no'


def test_eval_float_returns_default_on_unsupported(export_ctx, ev, tree, probe, mi_addon):
    ctx_module = importlib.import_module(
        f'{mi_addon}.io.exporter.export_context')
    export_ctx = ctx_module.ExportContext()
    noise = tree.nodes.new('ShaderNodeTexNoise')
    tree.links.new(noise.outputs['Fac'], probe.inputs['Strength'])
    assert ev.eval_float(export_ctx, probe.inputs['Strength'],
                         default=0.125) == 0.125


def test_eval_color_folds_spectrum(export_ctx, ev, tree, probe, mi_addon):
    ctx_module = importlib.import_module(
        f'{mi_addon}.io.exporter.export_context')
    export_ctx = ctx_module.ExportContext()
    node = tree.nodes.new('ShaderNodeRGB')
    node.outputs['Color'].default_value = (0.8, 0.6, 0.4, 1.0)
    tree.links.new(node.outputs['Color'], probe.inputs['Color'])
    spectrum = ev.eval_color(export_ctx, probe.inputs['Color'])
    assert spectrum['type'] == 'rgb'
    assert spectrum['value'] == pytest.approx((0.8, 0.6, 0.4))


def test_reroute_link_cycle_terminates(export_ctx, ev, tree, probe):
    # Blender permits link cycles made purely of reroutes; resolving one
    # must terminate instead of spinning forever
    r1 = tree.nodes.new('NodeReroute')
    r2 = tree.nodes.new('NodeReroute')
    tree.links.new(r1.outputs[0], r2.inputs[0])
    tree.links.new(r2.outputs[0], r1.inputs[0])
    result = fold_float(export_ctx, ev, tree, probe, r2.outputs[0])
    assert isinstance(result, (ev.Constant, ev.Unsupported))


def test_muted_node_link_cycle_terminates(export_ctx, ev, tree, probe):
    a = math_node(tree, 'ADD', 0.0, 0.0)
    b = math_node(tree, 'ADD', 0.0, 0.0)
    tree.links.new(a.outputs['Value'], b.inputs[0])
    tree.links.new(b.outputs['Value'], a.inputs[0])
    a.mute = True
    b.mute = True
    result = fold_float(export_ctx, ev, tree, probe, b.outputs['Value'])
    assert isinstance(result, (ev.Constant, ev.Unsupported))


def test_fold_link_cycle_terminates(export_ctx, ev, tree, probe):
    # A cycle through foldable nodes must not recurse without bound
    a = math_node(tree, 'ADD', 0.0, 0.0)
    b = math_node(tree, 'ADD', 0.0, 0.0)
    tree.links.new(a.outputs['Value'], b.inputs[0])
    tree.links.new(b.outputs['Value'], a.inputs[0])
    result = fold_float(export_ctx, ev, tree, probe, b.outputs['Value'])
    assert isinstance(result, (ev.Texture, ev.Unsupported))





def _make_group(name='TestGroup'):
    '''A shader node group with one Value input and one Value output,
    wired straight through: Group Input -> Group Output.'''
    group = bpy.data.node_groups.new(name, 'ShaderNodeTree')
    group.interface.new_socket('Amount', in_out='INPUT',
                               socket_type='NodeSocketFloat')
    group.interface.new_socket('Result', in_out='OUTPUT',
                               socket_type='NodeSocketFloat')
    g_in = group.nodes.new('NodeGroupInput')
    g_out = group.nodes.new('NodeGroupOutput')
    group.links.new(g_in.outputs['Amount'], g_out.inputs['Result'])
    return group, g_in, g_out
 
 
def test_group_passthrough(export_ctx, ev, tree, probe):
    '''A value linked into a group comes back out of it.'''
    group, _, _ = _make_group()
    node = tree.nodes.new('ShaderNodeValue')
    node.outputs['Value'].default_value = 7.0
    group_node = tree.nodes.new('ShaderNodeGroup')
    group_node.node_tree = group
    tree.links.new(node.outputs['Value'], group_node.inputs['Amount'])
    result = fold_float(export_ctx, ev, tree, probe, group_node.outputs['Result'])
    assert constant(result) == 7.0
 
 
 
def test_group_inner_math(export_ctx, ev, tree, probe):
    '''The interior is converted, not just passed through.'''
    group, g_in, g_out = _make_group('MathGroup')
    mul = group.nodes.new('ShaderNodeMath')
    mul.operation = 'MULTIPLY'
    mul.inputs[1].default_value = 3.0
    group.links.new(g_in.outputs['Amount'], mul.inputs[0])
    group.links.new(mul.outputs['Value'], g_out.inputs['Result'])
 
    node = tree.nodes.new('ShaderNodeValue')
    node.outputs['Value'].default_value = 2.0
    group_node = tree.nodes.new('ShaderNodeGroup')
    group_node.node_tree = group
    tree.links.new(node.outputs['Value'], group_node.inputs['Amount'])
    result = fold_float(export_ctx, ev, tree, probe, group_node.outputs['Result'])
    assert eval_float_texture(result) == 6.0
 
 
def test_nested_groups(export_ctx, ev, tree, probe):
    '''Group inside a group: the ascend step needs a stack, not a single
    saved node.'''
    inner, i_in, i_out = _make_group('Inner')
    outer, o_in, o_out = _make_group('Outer')
    inner_node = outer.nodes.new('ShaderNodeGroup')
    inner_node.node_tree = inner
    outer.links.new(o_in.outputs['Amount'], inner_node.inputs['Amount'])
    outer.links.new(inner_node.outputs['Result'], o_out.inputs['Result'])
 
    node = tree.nodes.new('ShaderNodeValue')
    node.outputs['Value'].default_value = 9.0
    group_node = tree.nodes.new('ShaderNodeGroup')
    group_node.node_tree = outer
    tree.links.new(node.outputs['Value'], group_node.inputs['Amount'])
    result = fold_float(export_ctx, ev, tree, probe, group_node.outputs['Result'])
    assert constant(result) == 9.0
 
 
def test_group_unsupported_node_inside(export_ctx, ev, tree, probe):
    '''An unsupported node inside a group is reported as unsupported --
    not as "GROUP is not supported".'''
    group, g_in, g_out = _make_group('NoiseGroup')
    noise = group.nodes.new('ShaderNodeTexNoise')
    group.links.new(noise.outputs['Fac'], g_out.inputs['Result'])
 
    group_node = tree.nodes.new('ShaderNodeGroup')
    group_node.node_tree = group
    result = fold_float(export_ctx, ev, tree, probe, group_node.outputs['Result'])
    assert isinstance(result, ev.Unsupported)
    assert 'TEX_NOISE' in result.reason
 
 
def test_group_with_no_tree(export_ctx, ev, tree, probe):
    '''A group node with no node_tree assigned must not crash.'''
    group_node = tree.nodes.new('ShaderNodeGroup')   # node_tree stays None
    probe.inputs['Strength'].default_value = 0.25
    tree.links.new(group_node.outputs[0], probe.inputs['Strength']) \
        if group_node.outputs else None
    result = ev.resolve(export_ctx, probe.inputs['Strength'])
    assert constant(result) == 0.25
