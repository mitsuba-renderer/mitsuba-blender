import bpy

import pytest

from fixtures import *

@pytest.mark.parametrize('scene, plugin', [
    ('scenes/rfilter_box.xml', 'box'),
    ('scenes/rfilter_tent.xml', 'tent'),
    ('scenes/rfilter_gaussian.xml', 'gaussian'),
])
def test_parsing_rfilters(mitsuba_parser_tester, scene, plugin):
    mitsuba_parser_tester.check_scene_plugin(scene, plugin)
