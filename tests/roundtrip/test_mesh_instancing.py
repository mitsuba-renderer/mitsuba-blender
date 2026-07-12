"""Instancing export tests: shared data becomes shapegroup + instances."""

import sys

import bpy
import pytest


@pytest.fixture
def exporter(mi_addon):
    """Returns a function that exports the current scene to a Mitsuba scene."""
    import mitsuba as mi

    def _export(directory, render=True):
        mi.set_variant('scalar_rgb')
        bpy.context.scene.render.engine = 'MITSUBA'
        converter = sys.modules[mi_addon].io.exporter.SceneConverter(render=render)
        converter.export_ctx.directory = str(directory)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        converter.scene_to_dict(depsgraph)
        return converter

    return _export


def count_types(converter, type_name):
    return sum(1 for v in converter.export_ctx.scene_data.values()
               if isinstance(v, dict) and v.get('type') == type_name)


def test_linked_duplicates_share_a_shapegroup(fresh_scene, exporter, tmp_path):
    b_cube = bpy.data.objects['Cube']
    duplicate = bpy.data.objects.new('Cube2', b_cube.data)
    duplicate.location = (4.0, 0.0, 0.0)
    bpy.context.collection.objects.link(duplicate)

    converter = exporter(tmp_path, render=False)
    assert count_types(converter, 'shapegroup') == 1
    assert count_types(converter, 'instance') == 2
    group = next(v for v in converter.export_ctx.scene_data.values()
                 if isinstance(v, dict) and v.get('type') == 'shapegroup')
    parts = [v for v in group.values()
             if isinstance(v, dict) and v.get('type') == 'ply']
    assert len(parts) == 1

    scene = converter.dict_to_scene()
    assert len(scene.shapes()) == 2


def test_material_override_prevents_instancing(fresh_scene, exporter, tmp_path):
    b_cube = bpy.data.objects['Cube']
    duplicate = bpy.data.objects.new('Cube2', b_cube.data)
    duplicate.location = (4.0, 0.0, 0.0)
    bpy.context.collection.objects.link(duplicate)
    override = bpy.data.materials.new('Override')
    duplicate.material_slots[0].link = 'OBJECT'
    duplicate.material_slots[0].material = override

    converter = exporter(tmp_path, render=False)
    assert count_types(converter, 'shapegroup') == 0
    assert count_types(converter, 'instance') == 0
    plys = [v for v in converter.export_ctx.scene_data.values()
            if isinstance(v, dict) and v.get('type') == 'ply']
    assert sorted(p['bsdf']['id'] for p in plys) \
        == ['mat-Material', 'mat-Override']


def test_collection_instances(fresh_scene, exporter, tmp_path):
    proto = bpy.data.collections.new('Proto')
    b_cube = bpy.data.objects['Cube']
    bpy.context.collection.objects.unlink(b_cube)
    proto.objects.link(b_cube)

    for i in range(3):
        empty = bpy.data.objects.new(f'Instancer{i}', None)
        empty.instance_type = 'COLLECTION'
        empty.instance_collection = proto
        empty.location = (4.0 * i, 0.0, 0.0)
        bpy.context.collection.objects.link(empty)

    converter = exporter(tmp_path, render=True)
    assert count_types(converter, 'shapegroup') == 1
    assert count_types(converter, 'instance') == 3

    scene = converter.dict_to_scene()
    assert len(scene.shapes()) == 3
    # The instance transforms are distinct
    centers = set()
    for shape in scene.shapes():
        bbox = shape.bbox()
        centers.add(round(0.5 * (bbox.min.x + bbox.max.x), 3))
    assert len(centers) == 3


def test_vertex_instancer_prototype_is_hidden(fresh_scene, exporter, tmp_path):
    b_cube = bpy.data.objects['Cube']
    bpy.ops.mesh.primitive_plane_add(size=10)
    plane = bpy.context.active_object
    b_cube.parent = plane
    plane.instance_type = 'VERTS'

    converter = exporter(tmp_path, render=False)
    # One instance per plane vertex; none at the prototype's own location
    assert count_types(converter, 'shapegroup') == 1
    assert count_types(converter, 'instance') == 4
    # The plane itself is still a plain top-level shape
    assert count_types(converter, 'ply') == 1


def test_particle_instances(fresh_scene, exporter, tmp_path):
    emitter = bpy.data.objects['Cube']
    psys = emitter.modifiers.new('ps', 'PARTICLE_SYSTEM').particle_system
    settings = psys.settings
    settings.count = 5
    settings.render_type = 'OBJECT'
    settings.frame_start = settings.frame_end = 1
    settings.physics_type = 'NO'
    bpy.ops.mesh.primitive_ico_sphere_add(location=(20.0, 0.0, 0.0))
    settings.instance_object = bpy.context.active_object
    bpy.context.view_layer.update()

    converter = exporter(tmp_path, render=False)
    assert count_types(converter, 'shapegroup') == 1
    # 5 particles plus the prototype object itself
    assert count_types(converter, 'instance') == 6

    scene = converter.dict_to_scene()
    assert len(scene.shapes()) == 7
