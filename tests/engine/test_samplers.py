import bpy

import pytest

from fixtures import *

@pytest.mark.parametrize('scene, plugin', [
    ('scenes/sampler_independent.xml', 'independent'),
    ('scenes/sampler_stratified.xml', 'stratified'),
    ('scenes/sampler_multijitter.xml', 'multijitter'),
])
def test_parsing_samplers(mitsuba_parser_tester, scene, plugin):
    mitsuba_parser_tester.check_scene_plugin(scene, plugin)
