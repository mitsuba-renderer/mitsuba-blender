import bpy

import pytest

from fixtures import *

@pytest.mark.parametrize('scene, plugin', [
    ('scenes/diffuse.xml', 'diffuse'),
    # ('scenes/null.xml', 'null'),
    # ('scenes/plastic.xml', 'plastic'),
    # ('scenes/roughplastic.xml', 'roughplastic'),
    # ('scenes/dielectric.xml', 'dielectric'),
    # ('scenes/thindielectric.xml', 'thindielectric'),
    # ('scenes/roughdielectric_anisotropic.xml', 'roughdielectric'),
    # ('scenes/roughdielectric_isotropic.xml', 'roughdielectric'),
    # ('scenes/conductor.xml', 'conductor'),
    # ('scenes/roughconductor_anisotropic.xml', 'roughconductor'),
    # ('scenes/roughconductor_isotropic.xml', 'roughconductor'),
    # ('scenes/bumpmap.xml', 'bumpmap'),
    # ('scenes/normalmap.xml', 'normalmap'),
    # ('scenes/blendbsdf.xml', 'blendbsdf'),
    # ('scenes/mask.xml', 'mask'),
    # ('scenes/twosided_1.xml', 'twosided'),
    # ('scenes/twosided_2.xml', 'twosided'),
    # ('scenes/principled.xml', 'principled'),
])
def test_parsing_materials(mitsuba_parser_tester, scene, plugin):
    mitsuba_parser_tester.check_scene_plugin(scene, plugin)
