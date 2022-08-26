import bpy

import pytest

from fixtures import *

@pytest.mark.parametrize('scene, plugin', [
    ('scenes/film_hdrfilm.xml', 'hdrfilm'), 
    ('scenes/film_hdrfilm_crop.xml', 'hdrfilm'),
])
@pytest.mark.skip(reason='Film export is not fully implemented yet')
def test_parsing_films(mitsuba_parser_tester, scene, plugin):
    mitsuba_parser_tester.check_scene_plugin(scene, plugin)
