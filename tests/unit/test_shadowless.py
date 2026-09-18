"""The shadowless BSDF plugin (shadow rays pass, camera and bounce rays
hit) and the exporter rule that wraps the materials of objects whose
Cycles shadow visibility is off."""

import sys

import bpy
import numpy as np
import pytest


@pytest.fixture(scope='session')
def plugins(mi_addon):
    return sys.modules[mi_addon].plugins


def variants():
    import mitsuba as mi
    names = ['scalar_rgb']
    for v in ('llvm_ad_rgb', 'llvm_rgb', 'cuda_ad_rgb'):
        if v in mi.variants():
            names.append(v)
            break
    return names


def use_variant(plugins, name):
    import mitsuba as mi
    mi.set_variant(name)
    plugins.register_plugins()


def occluder_scene(occluder):
    """A diffuse floor lit by a point light off to the side, with a small
    plane between them that casts a shadow next to where the camera sees
    the plane itself. The occluder is absent, shadowless or opaque."""
    import mitsuba as mi
    T = mi.ScalarTransform4f
    scene = {
        'type': 'scene',
        'integrator': {'type': 'path', 'max_depth': 3},
        'sensor': {
            'type': 'perspective', 'fov': 40,
            'to_world': T().look_at([0, 0, 6], [0, 0, 0], [0, 1, 0]),
            'film': {'type': 'hdrfilm', 'width': 32, 'height': 32,
                     'rfilter': {'type': 'box'}},
            'sampler': {'type': 'independent'},
        },
        'floor': {'type': 'rectangle', 'to_world': T().scale(4),
                  'bsdf': {'type': 'diffuse', 'reflectance': 0.5}},
        'light': {'type': 'point', 'position': [2, 0, 3], 'intensity': 10.0},
    }
    if occluder is not None:
        bsdf = {'type': 'diffuse', 'reflectance': 0.3}
        if occluder == 'shadowless':
            bsdf = {'type': 'shadowless', 'bsdf': bsdf}
        scene['occluder'] = {
            'type': 'rectangle',
            'to_world': T().translate([0, 0, 1]).scale(0.5),
            'bsdf': bsdf,
        }
    return scene


def occluder_of(scene):
    return [s for s in scene.shapes() if s.id() == 'occluder'][0]


######################
##   The plugin     ##
######################

@pytest.mark.parametrize('variant', variants())
def test_flags_add_a_null_component(plugins, variant):
    import mitsuba as mi
    use_variant(plugins, variant)
    nested = mi.load_dict({'type': 'diffuse'})
    bsdf = mi.load_dict({'type': 'shadowless', 'bsdf': {'type': 'diffuse'}})
    null = mi.BSDFFlags.Null | mi.BSDFFlags.FrontSide | mi.BSDFFlags.BackSide
    assert bsdf.component_count() == nested.component_count() + 1
    assert bsdf.flags(0) == nested.flags(0)
    assert bsdf.flags(1) == int(null)
    assert bsdf.flags() == int(nested.flags()) | int(null)

    scene = mi.load_dict(occluder_scene('shadowless'))
    assert occluder_of(scene).has_null()
    assert scene.has_null_shapes()


@pytest.mark.parametrize('variant', variants())
def test_shadow_rays_pass_while_camera_rays_hit(plugins, variant):
    import mitsuba as mi
    import drjit as dr
    use_variant(plugins, variant)
    scene = mi.load_dict(occluder_scene('shadowless'))
    opaque = mi.load_dict(occluder_scene('opaque'))

    # The shadow ray query of emitter sampling walks through the shape
    shadow_ray = mi.Ray3f(mi.Point3f(0, 0, 0.01), mi.Vector3f(0, 0, 1), 2.9)
    assert dr.all(scene.ray_test_tr(shadow_ray) == 1.0)
    assert dr.all(opaque.ray_test_tr(shadow_ray) == 0.0)
    # The shape sits in the null category of the acceleration structure,
    # which a query against the opaque shapes skips
    opaque_mask = int(mi.RayMask.Secondary) & int(mi.RayMask.Opaque)
    assert not dr.any(scene.ray_test(shadow_ray, False, ray_mask=opaque_mask))
    assert dr.any(opaque.ray_test(shadow_ray, False, ray_mask=opaque_mask))

    # Camera and bounce rays hit it like any surface
    camera_ray = mi.Ray3f(mi.Point3f(0, 0, 6), mi.Vector3f(0, 0, -1))
    for mask in (mi.RayMask.Primary, mi.RayMask.Secondary):
        si = scene.ray_intersect(camera_ray, int(mi.RayFlags.Default), False,
                                 ray_mask=int(mask))
        assert dr.allclose(si.t, 5.0)


@pytest.mark.parametrize('variant', variants())
def test_sampling_and_evaluation_follow_the_nested_bsdf(plugins, variant):
    import mitsuba as mi
    import drjit as dr
    use_variant(plugins, variant)
    nested = mi.load_dict({'type': 'diffuse', 'reflectance': 0.3})
    bsdf = mi.load_dict({'type': 'shadowless',
                         'bsdf': {'type': 'diffuse', 'reflectance': 0.3}})
    n = 4096
    si = dr.zeros(mi.SurfaceInteraction3f, n)
    si.sh_frame = mi.Frame3f(mi.Normal3f(0, 0, 1))
    si.n = si.sh_frame.n
    si.wi = mi.Vector3f(0.3, 0.2, 0.9327)
    sampler = mi.load_dict({'type': 'independent'})
    sampler.seed(0, n)
    s1, s2 = sampler.next_1d(), sampler.next_2d()
    ctx = mi.BSDFContext()

    bs, weight = bsdf.sample(ctx, si, s1, s2)
    sampled = np.array(bs.sampled_type)
    assert not np.any(sampled & int(mi.BSDFFlags.Null))
    ref_bs, ref_weight = nested.sample(ctx, si, s1, s2)
    assert np.allclose(np.array(bs.wo), np.array(ref_bs.wo))
    assert np.allclose(np.array(bs.pdf), np.array(ref_bs.pdf))
    assert np.allclose(np.array(weight), np.array(ref_weight))

    wo = bs.wo
    assert np.allclose(np.array(bsdf.eval(ctx, si, wo)),
                       np.array(nested.eval(ctx, si, wo)))
    assert np.allclose(np.array(bsdf.pdf(ctx, si, wo)),
                       np.array(nested.pdf(ctx, si, wo)))
    val, pdf = bsdf.eval_pdf(ctx, si, wo)
    assert np.allclose(np.array(val), np.array(nested.eval(ctx, si, wo)))
    assert np.allclose(np.array(pdf), np.array(nested.pdf(ctx, si, wo)))
    assert dr.all(bsdf.eval_null(si) == 1.0)
    features, ref_features = bsdf.eval_features(si), nested.eval_features(si)
    assert np.allclose(np.array(features.albedo), np.array(ref_features.albedo))
    assert np.allclose(np.array(features.roughness), np.array(ref_features.roughness))

    # A request for the null component alone yields nothing
    ctx.component = 1
    bs, weight = bsdf.sample(ctx, si, s1, s2)
    assert dr.all(bs.pdf == 0.0) and dr.all(weight == 0.0)
    assert dr.all(bsdf.eval(ctx, si, wo) == 0.0)
    assert dr.all(bsdf.pdf(ctx, si, wo) == 0.0)


@pytest.mark.parametrize('variant', variants())
def test_render_keeps_the_light_and_shows_the_shape(plugins, variant):
    import mitsuba as mi
    use_variant(plugins, variant)

    def render(occluder):
        scene = mi.load_dict(occluder_scene(occluder))
        return np.array(mi.render(scene, spp=64, seed=1))

    without, shadowless, opaque = (render(o) for o in
                                   (None, 'shadowless', 'opaque'))
    # The floor in the plane's shadow (x in [-1.75, -0.25])
    shadow = (slice(14, 18), slice(5, 9))
    # The plane as the camera sees it (|x| < 0.6)
    plane = (slice(14, 18), slice(14, 18))
    assert without[shadow].mean() > 0.04
    assert shadowless[shadow].mean() == pytest.approx(without[shadow].mean(),
                                                      rel=0.05)
    assert opaque[shadow].mean() == 0.0
    assert shadowless[plane].mean() == pytest.approx(opaque[plane].mean(),
                                                     rel=0.05)
    assert abs(shadowless[plane].mean() - without[plane].mean()) > 0.01


def test_traverse_reaches_the_nested_bsdf(plugins):
    import mitsuba as mi
    use_variant(plugins, 'scalar_rgb')
    bsdf = mi.load_dict({'type': 'shadowless',
                         'bsdf': {'type': 'diffuse', 'reflectance': 0.3}})
    params = mi.traverse(bsdf)
    assert 'nested_bsdf.reflectance.value' in params


######################
##   The exporter   ##
######################

@pytest.fixture
def exporter(mi_addon):
    import mitsuba as mi

    def _export(directory):
        mi.set_variant('scalar_rgb')
        bpy.context.scene.render.engine = 'MITSUBA'
        converter = sys.modules[mi_addon].io.exporter.SceneConverter(
            render=False)
        converter.export_ctx.directory = str(directory)
        converter.scene_to_dict(bpy.context.evaluated_depsgraph_get())
        return converter

    return _export


def shapes_of(converter):
    return [v for v in converter.export_ctx.scene_data.values()
            if isinstance(v, dict) and v.get('type') == 'packed']


def make_emissive_material(name='Glow'):
    b_mat = bpy.data.materials.new(name)
    b_mat.use_nodes = True
    tree = b_mat.node_tree
    tree.nodes.remove(tree.nodes['Principled BSDF'])
    node = tree.nodes.new('ShaderNodeEmission')
    node.inputs['Strength'].default_value = 2.0
    tree.links.new(node.outputs['Emission'],
                   tree.nodes['Material Output'].inputs['Surface'])
    return b_mat


def mesh_of(scene):
    import mitsuba as mi
    shape, = [s for s in scene.shapes() if isinstance(s, mi.Mesh)]
    return shape


def add_cube_copy(name, source, location):
    other = bpy.data.objects.new(name, bpy.data.meshes.new_from_object(source))
    other.location = location
    bpy.context.collection.objects.link(other)
    return other


def test_shadowless_object_wraps_its_material(fresh_scene, exporter,
                                              tmp_path):
    # The default light would add a cycles_lights shape with a null BSDF
    bpy.data.objects.remove(bpy.data.objects['Light'])
    cube = bpy.data.objects['Cube']
    cube.visible_shadow = False
    converter = exporter(tmp_path)
    ctx = converter.export_ctx
    shape, = shapes_of(converter)
    assert 'visibility' not in shape
    assert shape['bsdf'] == ctx.create_ref('mat-Material-shadowless')
    assert ctx.data_get('mat-Material-shadowless') == {
        'type': 'shadowless', 'bsdf': ctx.create_ref('mat-Material')}
    scene = converter.dict_to_scene()
    assert scene.has_null_shapes()
    assert mesh_of(scene).has_null()


def test_shadowless_object_survives_the_xml(fresh_scene, exporter, tmp_path):
    cube = bpy.data.objects['Cube']
    cube.visible_shadow = False
    converter = exporter(tmp_path)
    xml = str(tmp_path / 'scene.xml')
    converter.dict_to_xml(xml)
    import mitsuba as mi
    assert mesh_of(mi.load_file(xml)).has_null()
    # The importer unwraps the material again
    assert bpy.ops.import_scene.mitsuba(filepath=xml) == {'FINISHED'}


def test_shared_material_keeps_both_variants(fresh_scene, exporter, tmp_path):
    cube = bpy.data.objects['Cube']
    other = add_cube_copy('Other', cube, (4.0, 0.0, 0.0))
    other.visible_shadow = False
    converter = exporter(tmp_path)
    refs = sorted(s['bsdf']['id'] for s in shapes_of(converter))
    assert refs == ['mat-Material', 'mat-Material-shadowless']
    assert converter.dict_to_scene() is not None


def test_shadowless_objects_share_one_wrapper(fresh_scene, exporter,
                                              tmp_path):
    cube = bpy.data.objects['Cube']
    cube.visible_shadow = False
    other = add_cube_copy('Other', cube, (4.0, 0.0, 0.0))
    other.visible_shadow = False
    converter = exporter(tmp_path)
    refs = [s['bsdf']['id'] for s in shapes_of(converter)]
    assert refs == ['mat-Material-shadowless'] * 2
    wrappers = [k for k in converter.export_ctx.scene_data
                if k.endswith('-shadowless')]
    assert wrappers == ['mat-Material-shadowless']


def test_emissive_shadowless_object_keeps_emitting(fresh_scene, exporter,
                                                   tmp_path):
    bpy.data.objects.remove(bpy.data.objects['Light'])
    cube = bpy.data.objects['Cube']
    cube.data.materials.clear()
    cube.data.materials.append(make_emissive_material())
    cube.visible_shadow = False
    converter = exporter(tmp_path)
    shape, = shapes_of(converter)
    assert shape['bsdf'] == converter.export_ctx.create_ref(
        'mat-Glow-shadowless')
    assert shape['emitter']['type'] == 'area'
    scene = converter.dict_to_scene()
    assert len(scene.emitters()) == 1


def test_object_without_material_is_wrapped_too(fresh_scene, exporter,
                                                tmp_path):
    cube = bpy.data.objects['Cube']
    cube.data.materials.clear()
    cube.visible_shadow = False
    converter = exporter(tmp_path)
    shape, = shapes_of(converter)
    assert shape['bsdf'] == converter.export_ctx.create_ref(
        'default-bsdf-shadowless')


def test_camera_only_object_needs_no_wrapper(fresh_scene, exporter, tmp_path):
    """Secondary rays never reach a camera-only shape, shadow rays
    included."""
    cube = bpy.data.objects['Cube']
    for flag in ('visible_diffuse', 'visible_glossy', 'visible_transmission',
                 'visible_shadow'):
        setattr(cube, flag, False)
    converter = exporter(tmp_path)
    shape, = shapes_of(converter)
    assert shape['visibility'] == 'primary'
    assert shape['bsdf'] == converter.export_ctx.create_ref('mat-Material')

