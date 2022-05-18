import os

import bpy

import pytest

from fixtures import *

@pytest.mark.parametrize("xml_scene", ["scenes/test1.xml"])
def test_round_trip(xml_scene, resource_resolver, mitsuba_scene_ztest):
    resolution = (1280, 720)
    sample_budget = int(2e6)
    pixel_count = resolution[0] * resolution[1]
    spp = sample_budget // pixel_count

    significance_level = 0.01

    ref_scene_file = resource_resolver.get_absolute_resource_path(xml_scene)
    ref_scene_name, _ = os.path.splitext(os.path.basename(ref_scene_file))
    test_output_dir = resource_resolver.ensure_resource_dir(f'out/{ref_scene_name}')
    output_scene_file = os.path.join(test_output_dir, f'{ref_scene_name}_out.xml')

    assert bpy.ops.import_scene.mitsuba2(filepath=ref_scene_file) == {'FINISHED'}
    assert bpy.ops.export_scene.mitsuba2(filepath=output_scene_file, ignore_background=True) == {'FINISHED'}

    assert mitsuba_scene_ztest.compare_scenes(ref_scene_file, output_scene_file, spp, resolution, test_output_dir)