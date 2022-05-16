import bpy

import pytest

from fixtures import test_resource_resolver, mitsuba_scene_parser

@pytest.mark.parametrize("xml_scene", ["scenes/test1.xml"])
def test_importer_initializes_mitsuba_renderer(test_resource_resolver, xml_scene):
    scene_file = test_resource_resolver.get_absolute_resource_path(xml_scene)
    
    assert bpy.ops.import_scene.mitsuba2(filepath=scene_file) == {'FINISHED'}

    assert bpy.context.scene.render.engine == 'MITSUBA2'
    assert bpy.context.scene.mitsuba.variant == 'scalar_rgb'

@pytest.mark.parametrize("xml_scene", ["scenes/integrator_path.xml"])
def test_importer_path_integrator(test_resource_resolver, mitsuba_scene_parser, xml_scene):
    scene_file = test_resource_resolver.get_absolute_resource_path(xml_scene)
    mitsuba_scene_parser.load_xml(scene_file)
    
    mi_integrator = mitsuba_scene_parser.get_props_by_name('path')
    assert mi_integrator
    
    assert bpy.ops.import_scene.mitsuba2(filepath=scene_file) == {'FINISHED'}

    bl_scene = bpy.context.scene
    assert bl_scene.mitsuba.active_integrator == 'path'
    assert bl_scene.mitsuba.available_integrators.path.max_depth == mi_integrator.get('max_depth')
    assert bl_scene.mitsuba.available_integrators.path.rr_depth == mi_integrator.get('rr_depth')
    assert bl_scene.mitsuba.available_integrators.path.hide_emitters == mi_integrator.get('hide_emitters')

    # assert len(mi_integrator.unqueried()) == 0

@pytest.mark.parametrize("xml_scene", ["scenes/integrator_moment.xml"])
def test_importer_moment_integrator(test_resource_resolver, mitsuba_scene_parser, xml_scene):
    scene_file = test_resource_resolver.get_absolute_resource_path(xml_scene)
    mitsuba_scene_parser.load_xml(scene_file)
    
    mi_integrator = mitsuba_scene_parser.get_props_by_name('moment')
    assert mi_integrator

    mi_child_integrator = mitsuba_scene_parser.get_props_by_name('path')
    assert mi_child_integrator
    
    assert bpy.ops.import_scene.mitsuba2(filepath=scene_file) == {'FINISHED'}

    bl_scene = bpy.context.scene
    assert bl_scene.mitsuba.active_integrator == 'moment'
    assert bl_scene.mitsuba.available_integrators.moment.integrators.count == 1
    bl_child_integrator = bl_scene.mitsuba.available_integrators.moment.integrators.collection[0]
    assert bl_child_integrator.active_integrator == 'path'
    assert bl_child_integrator.available_integrators.path.max_depth == mi_child_integrator.get('max_depth')
    assert bl_child_integrator.available_integrators.path.rr_depth == mi_child_integrator.get('rr_depth')
    assert bl_child_integrator.available_integrators.path.hide_emitters == mi_child_integrator.get('hide_emitters')
    
    # assert len(mi_integrator.unqueried()) == 0

@pytest.mark.parametrize("xml_scene", ["scenes/sampler_independent.xml"])
def test_importer_independent_sampler(test_resource_resolver, mitsuba_scene_parser, xml_scene):
    scene_file = test_resource_resolver.get_absolute_resource_path(xml_scene)
    mitsuba_scene_parser.load_xml(scene_file)
    
    mi_sampler = mitsuba_scene_parser.get_props_by_name('independent')
    assert mi_sampler

    assert bpy.ops.import_scene.mitsuba2(filepath=scene_file) == {'FINISHED'}

    bl_camera = bpy.context.scene.camera.data.mitsuba
    assert bl_camera.active_sampler == 'independent'
    assert bl_camera.samplers.independent.sample_count == mi_sampler.get('sample_count')
    assert bl_camera.samplers.independent.seed == mi_sampler.get('seed')

    # assert len(mi_sampler.unqueried()) == 0

@pytest.mark.parametrize("xml_scene", ["scenes/sampler_stratified.xml"])
def test_importer_stratified_sampler(test_resource_resolver, mitsuba_scene_parser, xml_scene):
    scene_file = test_resource_resolver.get_absolute_resource_path(xml_scene)
    mitsuba_scene_parser.load_xml(scene_file)
    
    mi_sampler = mitsuba_scene_parser.get_props_by_name('stratified')
    assert mi_sampler

    assert bpy.ops.import_scene.mitsuba2(filepath=scene_file) == {'FINISHED'}

    bl_camera = bpy.context.scene.camera.data.mitsuba
    assert bl_camera.active_sampler == 'stratified'
    assert bl_camera.samplers.stratified.sample_count == mi_sampler.get('sample_count')
    assert bl_camera.samplers.stratified.seed == mi_sampler.get('seed')
    assert bl_camera.samplers.stratified.jitter == mi_sampler.get('jitter')

    # assert len(mi_sampler.unqueried()) == 0

@pytest.mark.parametrize("xml_scene", ["scenes/sampler_multijitter.xml"])
def test_importer_multijitter_sampler(test_resource_resolver, mitsuba_scene_parser, xml_scene):
    scene_file = test_resource_resolver.get_absolute_resource_path(xml_scene)
    mitsuba_scene_parser.load_xml(scene_file)
    
    mi_sampler = mitsuba_scene_parser.get_props_by_name('multijitter')
    assert mi_sampler

    assert bpy.ops.import_scene.mitsuba2(filepath=scene_file) == {'FINISHED'}

    bl_camera = bpy.context.scene.camera.data.mitsuba
    assert bl_camera.active_sampler == 'multijitter'
    assert bl_camera.samplers.multijitter.sample_count == mi_sampler.get('sample_count')
    assert bl_camera.samplers.multijitter.seed == mi_sampler.get('seed')
    assert bl_camera.samplers.multijitter.jitter == mi_sampler.get('jitter')

    # assert len(mi_sampler.unqueried()) == 0

@pytest.mark.parametrize("xml_scene", ["scenes/rfilter_box.xml"])
def test_importer_box_rfilter(test_resource_resolver, mitsuba_scene_parser, xml_scene):
    scene_file = test_resource_resolver.get_absolute_resource_path(xml_scene)
    mitsuba_scene_parser.load_xml(scene_file)
    
    mi_rfilter = mitsuba_scene_parser.get_props_by_name('box')
    assert mi_rfilter

    assert bpy.ops.import_scene.mitsuba2(filepath=scene_file) == {'FINISHED'}

    bl_camera = bpy.context.scene.camera.data.mitsuba
    assert bl_camera.active_rfilter == 'box'
    
    # assert len(mi_rfilter.unqueried()) == 0

@pytest.mark.parametrize("xml_scene", ["scenes/rfilter_tent.xml"])
def test_importer_tent_rfilter(test_resource_resolver, mitsuba_scene_parser, xml_scene):
    scene_file = test_resource_resolver.get_absolute_resource_path(xml_scene)
    mitsuba_scene_parser.load_xml(scene_file)
    
    mi_rfilter = mitsuba_scene_parser.get_props_by_name('tent')
    assert mi_rfilter

    assert bpy.ops.import_scene.mitsuba2(filepath=scene_file) == {'FINISHED'}

    bl_camera = bpy.context.scene.camera.data.mitsuba
    assert bl_camera.active_rfilter == 'tent'
    
    # assert len(mi_rfilter.unqueried()) == 0

@pytest.mark.parametrize("xml_scene", ["scenes/rfilter_gaussian.xml"])
def test_importer_gaussian_rfilter(test_resource_resolver, mitsuba_scene_parser, xml_scene):
    scene_file = test_resource_resolver.get_absolute_resource_path(xml_scene)
    mitsuba_scene_parser.load_xml(scene_file)
    
    mi_rfilter = mitsuba_scene_parser.get_props_by_name('gaussian')
    assert mi_rfilter

    assert bpy.ops.import_scene.mitsuba2(filepath=scene_file) == {'FINISHED'}

    bl_camera = bpy.context.scene.camera.data.mitsuba
    assert bl_camera.active_rfilter == 'gaussian'
    assert bl_camera.rfilters.gaussian.stddev == mi_rfilter.get('stddev')
    
    # assert len(mi_rfilter.unqueried()) == 0

@pytest.mark.parametrize("xml_scene", ["scenes/film_hdrfilm.xml", "scenes/film_hdrfilm_crop.xml"])
def test_importer_hdrfilm_film(test_resource_resolver, mitsuba_scene_parser, xml_scene):
    scene_file = test_resource_resolver.get_absolute_resource_path(xml_scene)
    mitsuba_scene_parser.load_xml(scene_file)
    
    mi_film = mitsuba_scene_parser.get_props_by_name('hdrfilm')
    assert mi_film

    assert bpy.ops.import_scene.mitsuba2(filepath=scene_file) == {'FINISHED'}

    bl_render = bpy.context.scene.render
    assert bl_render.resolution_percentage == 100
    assert bl_render.resolution_x == mi_film.get('width')
    assert bl_render.resolution_y == mi_film.get('height')
    assert bl_render.image_settings.file_format == 'OPEN_EXR'
    assert bl_render.image_settings.color_mode == 'RGBA'
    assert bl_render.image_settings.color_depth == '32'
    if 'crop' in xml_scene:
        assert bl_render.use_border == True
        assert bl_render.border_min_x == 0.0
        assert bl_render.border_min_y == 0.0
        assert bl_render.border_max_x == 0.5
        assert bl_render.border_max_y == 0.5
    else:
        assert bl_render.use_border == False

    # assert len(mi_film.unqueried()) == 0