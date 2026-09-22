"""Hair particle systems exported as linearcurve shapes."""

import os
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


def curve_shapes(converter):
    return [v for v in converter.export_ctx.scene_data.values()
            if isinstance(v, dict) and v.get('type') == 'linearcurve']


def add_hair(b_object, name='hair', count=4, children='NONE'):
    psys = b_object.modifiers.new(name, 'PARTICLE_SYSTEM').particle_system
    settings = psys.settings
    settings.type = 'HAIR'
    settings.count = count
    settings.hair_length = 0.5
    settings.child_type = children
    bpy.context.view_layer.update()
    return psys


def read_strands(directory, shape):
    """Read the curve entry of a shape from the exported container into a
    list of [(x, y, z, radius), ...] strands."""
    import mitsuba as mi
    import numpy as np
    pf = mi.PackedFile.open(os.path.join(directory, shape['filename']))
    e = pf.entry(shape['index'])
    assert e.read(4) == b'CURV'
    assert e.read_uint32() == 1
    n_curves, n_points = e.read_uint32(), e.read_uint32()
    offsets = np.frombuffer(e.read_array((n_curves + 1) * 4), dtype=np.uint32)
    points = np.frombuffer(e.read_array(n_points * 16),
                           dtype=np.float32).reshape(-1, 4)
    return [[tuple(p) for p in points[a:b]]
            for a, b in zip(offsets[:-1], offsets[1:])]


def test_hair_exports_a_linearcurve(fresh_scene, exporter, tmp_path):
    add_hair(bpy.data.objects['Cube'])

    converter = exporter(tmp_path, render=False)
    shapes = curve_shapes(converter)
    assert len(shapes) == 1

    assert shapes[0]['filename'] == 'curves.packed'
    converter.export_ctx.finalize_packed()
    strands = read_strands(str(tmp_path), shapes[0])
    assert len(strands) > 0
    for strand in strands:
        assert len(strand) >= 2
        assert all(len(point) == 4 for point in strand)


def test_hair_radius_follows_the_particle_settings(fresh_scene, exporter,
                                                   tmp_path):
    psys = add_hair(bpy.data.objects['Cube'])
    settings = psys.settings
    settings.root_radius = 0.2
    settings.tip_radius = 0.2
    settings.radius_scale = 0.5
    settings.use_close_tip = False
    bpy.context.view_layer.update()

    converter = exporter(tmp_path, render=False)
    converter.export_ctx.finalize_packed()
    strands = read_strands(str(tmp_path), curve_shapes(converter)[0])
    # The root and tip diameters agree, so every control point has the same
    # radius, half the diameter times the scale
    expected = 0.5 * 0.5 * 0.2
    for strand in strands:
        for point in strand:
            assert point[3] == pytest.approx(expected, rel=1e-4)


def test_close_tip_ends_the_strand_at_zero_radius(fresh_scene, exporter,
                                                  tmp_path):
    psys = add_hair(bpy.data.objects['Cube'])
    psys.settings.use_close_tip = True
    bpy.context.view_layer.update()

    converter = exporter(tmp_path, render=False)
    converter.export_ctx.finalize_packed()
    for strand in read_strands(str(tmp_path), curve_shapes(converter)[0]):
        assert strand[-1][3] == 0.0
        assert strand[0][3] > 0.0


def test_hair_uses_the_material_slot_of_the_particle_system(fresh_scene,
                                                            exporter,
                                                            tmp_path):
    b_object = bpy.data.objects['Cube']
    b_object.data.materials.clear()
    b_object.data.materials.append(bpy.data.materials.new('Skin'))
    b_object.data.materials.append(bpy.data.materials.new('Fur'))
    assert [s.material.name for s in b_object.material_slots] == ['Skin', 'Fur']
    psys = add_hair(b_object)
    # ParticleSettings.material is a one-based slot index
    psys.settings.material = 2
    bpy.context.view_layer.update()

    converter = exporter(tmp_path, render=False)
    assert curve_shapes(converter)[0]['bsdf']['id'] == 'mat-Fur'


def test_instanced_particle_systems_are_not_exported_as_curves(fresh_scene,
                                                               exporter,
                                                               tmp_path):
    # Render types other than PATH reach the exporter as depsgraph instances
    psys = add_hair(bpy.data.objects['Cube'])
    psys.settings.render_type = 'OBJECT'
    bpy.ops.mesh.primitive_ico_sphere_add(location=(20.0, 0.0, 0.0))
    psys.settings.instance_object = bpy.context.active_object
    bpy.context.view_layer.update()

    converter = exporter(tmp_path, render=False)
    assert curve_shapes(converter) == []


def test_mitsuba_loads_the_exported_curves(fresh_scene, exporter, tmp_path):
    import mitsuba as mi

    add_hair(bpy.data.objects['Cube'])
    converter = exporter(tmp_path, render=False)
    converter.export_ctx.finalize_packed()
    shape = curve_shapes(converter)[0]

    # The film of the exported scene needs a JIT variant, so the curves are
    # loaded on their own
    curves = mi.load_dict({
        'type': 'linearcurve',
        'filename': os.path.join(str(tmp_path), shape['filename']),
        'index': shape['index'],
    })
    assert curves.bbox().valid()
    assert (tmp_path / 'curves.packed').is_file()
