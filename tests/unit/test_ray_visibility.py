"""Cycles ray visibility flags <-> the Mitsuba ``visibility`` property."""

import importlib
import sys

import bpy
import pytest
from bpy_extras.io_utils import axis_conversion

FLAGS = ('visible_camera', 'visible_diffuse', 'visible_glossy',
         'visible_transmission', 'visible_shadow')


@pytest.fixture(scope='session')
def export_module(mi_addon):
    return importlib.import_module(f'{mi_addon}.convert.export')


@pytest.fixture(scope='session')
def lights(mi_addon):
    return importlib.import_module(f'{mi_addon}.convert.export.lights')


@pytest.fixture(scope='session')
def world(mi_addon):
    return importlib.import_module(f'{mi_addon}.convert.export.world')


@pytest.fixture
def export_ctx(mi_addon, tmp_path):
    import mitsuba as mi
    mi.set_variant('scalar_rgb')
    module = importlib.import_module(f'{mi_addon}.io.exporter.export_context')
    ctx = module.ExportContext()
    ctx.directory = str(tmp_path)
    ctx.axis_mat = axis_conversion(to_forward='-Z', to_up='Y').to_4x4()
    return ctx


@pytest.fixture
def log_capture(export_ctx):
    logs = []
    export_ctx.log = lambda msg, level='INFO': logs.append((level, msg))
    return logs


@pytest.fixture
def exporter(mi_addon):
    """Exports the current scene and returns the SceneConverter."""
    import mitsuba as mi

    def _export(directory, render=False):
        mi.set_variant('scalar_rgb')
        bpy.context.scene.render.engine = 'MITSUBA'
        converter = sys.modules[mi_addon].io.exporter.SceneConverter(
            render=render)
        converter.export_ctx.directory = str(directory)
        converter.scene_to_dict(bpy.context.evaluated_depsgraph_get())
        return converter

    return _export


def set_flags(b_object, camera=True, diffuse=True, glossy=True,
              transmission=True, shadow=True):
    b_object.visible_camera = camera
    b_object.visible_diffuse = diffuse
    b_object.visible_glossy = glossy
    b_object.visible_transmission = transmission
    b_object.visible_shadow = shadow


def make_light(light_type, name='TestLight', **data_props):
    data = bpy.data.lights.new(name, light_type)
    for key, value in data_props.items():
        setattr(data, key, value)
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.update()
    return obj


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


def entries_of(export_ctx, type_name):
    return [v for v in export_ctx.scene_data.values()
            if isinstance(v, dict) and v.get('type') == type_name]


def shapes_of(converter, type_name='packed'):
    return entries_of(converter.export_ctx, type_name)


##########################
##   The flag mapping   ##
##########################

@pytest.mark.parametrize('flags, plain, emissive', [
    # camera diffuse glossy transmission shadow
    ((True, True, True, True, True), 'all', 'all'),
    # Camera-only glass: light passes, the camera still sees it
    ((True, False, False, False, False), 'primary', 'primary'),
    # A window pane or a backdrop that casts no shadow but appears in
    # bounces keeps its bounce visibility
    ((True, True, True, True, False), 'all', 'all'),
    ((True, True, False, True, False), 'all', 'all'),
    # Emissive and shadow-casting: a visible light source
    ((True, True, False, False, True), 'all', 'all'),
    # A light plane hidden from the camera
    ((False, True, True, True, True), 'secondary', 'secondary'),
    ((False, True, False, False, False), 'secondary', 'secondary'),
    # Shadow rays alone never reach a light source
    ((False, False, False, False, True), 'secondary', None),
    ((False, False, False, False, False), None, None),
])
def test_ray_visibility_mapping(fresh_scene, export_module, flags, plain,
                                emissive):
    b_object = bpy.data.objects['Cube']
    set_flags(b_object, *flags)
    assert export_module.ray_visibility(b_object, False) == plain
    assert export_module.ray_visibility(b_object, True) == emissive


@pytest.mark.parametrize('caustics, camera, plain, emissive', [
    (True, True, 'all', 'all'),
    # Only camera paths reach the emitter through transmission, and
    # Mitsuba's primary mask survives delta refraction
    (False, True, 'all', 'primary'),
    (False, False, 'secondary', 'secondary'),
])
def test_transmission_only_visibility(fresh_scene, export_module, caustics,
                                      camera, plain, emissive):
    bpy.context.scene.cycles.caustics_refractive = caustics
    b_object = bpy.data.objects['Cube']
    set_flags(b_object, camera=camera, diffuse=False, glossy=False,
              shadow=False)
    assert export_module.ray_visibility(b_object, False) == plain
    assert export_module.ray_visibility(b_object, True) == emissive


###############
##   Meshes  ##
###############

@pytest.mark.parametrize('flags, emissive, expected', [
    (dict(), False, 'all'),
    (dict(diffuse=False, glossy=False, transmission=False, shadow=False),
     False, 'primary'),
    # A camera-invisible object still casts shadows
    (dict(camera=False), False, 'secondary'),
    (dict(camera=False, diffuse=False, glossy=False, transmission=False,
          shadow=False), False, None),
    # Emitters do not occlude, so the shadow flag has no say
    (dict(camera=False, shadow=False), True, 'secondary'),
    # A camera-visible emissive mesh that casts no shadow still lights
    # and blocks bounce rays
    (dict(glossy=False, shadow=False), True, 'all'),
    (dict(camera=False, diffuse=False, glossy=False, transmission=False),
     True, None),
])
def test_shape_visibility(fresh_scene, exporter, tmp_path, flags, emissive,
                          expected):
    b_object = bpy.data.objects['Cube']
    if emissive:
        b_object.data.materials.clear()
        b_object.data.materials.append(make_emissive_material())
    set_flags(b_object, **flags)
    converter = exporter(tmp_path)
    shapes = shapes_of(converter)
    if expected is None:
        assert shapes == []
        return
    shape, = shapes
    assert shape.get('visibility', 'all') == expected
    if emissive:
        # Cycles hides the object from some ray types only, so the shape
        # keeps the BSDF of its material and its emitter
        assert shape['bsdf'] == converter.export_ctx.create_ref('mat-Glow')
        assert 'visible' not in shape['emitter']


def test_visibility_separates_instances(fresh_scene, exporter, tmp_path):
    bpy.data.objects.remove(bpy.data.objects['Light'])
    b_cube = bpy.data.objects['Cube']
    duplicate = bpy.data.objects.new('Cube2', b_cube.data)
    duplicate.location = (4.0, 0.0, 0.0)
    bpy.context.collection.objects.link(duplicate)
    set_flags(duplicate, camera=False)

    converter = exporter(tmp_path)
    # Different visibility classes cannot share a shapegroup
    assert shapes_of(converter, 'shapegroup') == []
    shapes = shapes_of(converter)
    assert sorted(s.get('visibility', 'all') for s in shapes) \
        == ['all', 'secondary']


def test_shared_visibility_keeps_instancing(fresh_scene, exporter, tmp_path):
    bpy.data.objects.remove(bpy.data.objects['Light'])
    b_cube = bpy.data.objects['Cube']
    duplicate = bpy.data.objects.new('Cube2', b_cube.data)
    duplicate.location = (4.0, 0.0, 0.0)
    bpy.context.collection.objects.link(duplicate)
    set_flags(b_cube, camera=False)
    set_flags(duplicate, camera=False)

    converter = exporter(tmp_path)
    groups = shapes_of(converter, 'shapegroup')
    assert len(groups) == 1
    parts = [v for v in groups[0].values()
             if isinstance(v, dict) and v.get('type') == 'packed']
    assert [p['visibility'] for p in parts] == ['secondary']
    instances = shapes_of(converter, 'instance')
    assert len(instances) == 2
    assert all('visibility' not in i for i in instances)
    scene = converter.dict_to_scene()
    assert len(scene.shapes()) == 2


###############
##   Lights  ##
###############

@pytest.mark.parametrize('flags, expected', [
    (dict(), None),
    (dict(camera=False), 'secondary'),
    (dict(diffuse=False, glossy=False, transmission=False), 'primary'),
    # Lights never occlude in Cycles, so their shadow flag has no say
    (dict(glossy=False, shadow=False), None),
])
def test_area_light_visibility(fresh_scene, export_ctx, lights, flags,
                               expected):
    obj = make_light('AREA', energy=10.0)
    set_flags(obj, **flags)
    params = lights.convert_light(export_ctx, obj)
    assert params.get('visibility') == expected
    assert 'visible' not in params['emitter']

    import mitsuba as mi
    scene = mi.load_dict({'type': 'scene', 'light': params})
    assert len(scene.emitters()) == 1


@pytest.mark.parametrize('light_type', ['POINT', 'SPOT', 'SUN'])
def test_delta_light_carries_no_visibility(fresh_scene, export_ctx, lights,
                                           light_type):
    obj = make_light(light_type, energy=10.0, shadow_soft_size=0.0)
    set_flags(obj, camera=False, glossy=False)
    params = lights.convert_light(export_ctx, obj)
    assert 'visibility' not in params
    assert 'visible' not in params

    import mitsuba as mi
    scene = mi.load_dict({'type': 'scene', 'light': params})
    assert len(scene.emitters()) == 1


def test_delta_light_seen_only_by_camera_is_skipped(fresh_scene, export_ctx,
                                                     lights, log_capture):
    obj = make_light('POINT', energy=10.0, shadow_soft_size=0.0)
    set_flags(obj, diffuse=False, glossy=False, transmission=False)
    assert lights.convert_light(export_ctx, obj) is None
    assert any('only visible to camera rays' in msg for _, msg in log_capture)


def test_light_hidden_from_every_ray_is_skipped(fresh_scene, export_ctx,
                                                 lights, log_capture):
    obj = make_light('AREA', energy=10.0)
    # Shadow rays alone never reach a light
    set_flags(obj, camera=False, diffuse=False, glossy=False,
              transmission=False)
    assert lights.convert_light(export_ctx, obj) is None
    assert any('hidden from every ray type' in msg for _, msg in log_capture)


def test_skipped_light_does_not_reach_the_scene(fresh_scene, exporter,
                                                tmp_path):
    light = bpy.data.objects['Light']
    light.data.shadow_soft_size = 0.0
    set_flags(light, camera=False, diffuse=False, glossy=False,
              transmission=False)
    assert shapes_of(exporter(tmp_path), 'point') == []


##############
##   World  ##
##############

def make_world(name='TestWorld'):
    b_world = bpy.data.worlds.new(name)
    b_world.use_nodes = True
    background = b_world.node_tree.nodes['Background']
    background.inputs['Color'].default_value = (0.2, 0.4, 0.6, 1.0)
    background.inputs['Strength'].default_value = 2.0
    return b_world


@pytest.mark.parametrize('flags, expected', [
    (dict(), None),
    (dict(camera=False), 'secondary'),
    (dict(diffuse=False, glossy=False, transmission=False), 'primary'),
    (dict(camera=False, diffuse=False, glossy=False, transmission=False),
     'skipped'),
])
def test_world_visibility(fresh_scene, export_ctx, world, log_capture, flags,
                          expected):
    b_world = make_world()
    for flag, value in flags.items():
        setattr(b_world.cycles_visibility, flag, value)
    world.export_world(export_ctx, b_world)
    if expected == 'skipped':
        assert entries_of(export_ctx, 'constant') == []
        assert any('hidden from every ray' in msg for _, msg in log_capture)
        return
    params, = entries_of(export_ctx, 'constant')
    assert params.get('visibility') == expected

    import mitsuba as mi
    scene = mi.load_dict({'type': 'scene', 'world': params})
    assert len(scene.emitters()) == 1
