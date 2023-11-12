import bpy

import pytest

from fixtures import *

@pytest.mark.parametrize('scene, plugin', [
    ('scenes/integrator_path.xml', 'path'),
    ('scenes/integrator_moment.xml', 'moment'),
])
def test_parsing_integrators(mitsuba_parser_tester, scene, plugin):
    mitsuba_parser_tester.check_scene_plugin(scene, plugin)
