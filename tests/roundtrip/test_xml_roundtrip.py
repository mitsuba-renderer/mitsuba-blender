"""Full-scene round trip: import an XML scene, export it again and compare
renders of the two files with a statistical z-test."""

import os

import bpy

from ztest import MitsubaRenderTester, MitsubaSceneRenderer

SCENES = os.path.join(os.path.dirname(__file__), '..', 'res', 'scenes')


def test_xml_scene_ztest_roundtrip(mi_addon, fresh_scene, tmp_path):
    resolution = (1280, 720)
    sample_budget = int(2e6)
    spp = sample_budget // (resolution[0] * resolution[1])

    ref_scene_file = os.path.join(SCENES, 'test1.xml')
    output_scene_file = str(tmp_path / 'test1_out.xml')

    assert bpy.ops.import_scene.mitsuba(
        filepath=ref_scene_file, import_render_settings=True) == {'FINISHED'}
    bpy.context.scene.render.engine = 'MITSUBA'
    assert bpy.ops.export_scene.mitsuba(
        filepath=output_scene_file, ignore_background=True) == {'FINISHED'}

    tester = MitsubaRenderTester(MitsubaSceneRenderer())
    assert tester.compare_scenes(ref_scene_file, output_scene_file, spp,
                                 resolution, str(tmp_path))
