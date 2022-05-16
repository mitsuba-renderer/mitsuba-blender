import pytest

import os

class TestResourceResolver:
    def __init__(self):
        self.root = os.path.join(os.getcwd(), 'tests/res')

    def get_absolute_resource_path(self, relative_path):
        return os.path.join(self.root, relative_path)

class MitsubaSceneParser:
    def __init__(self):
        self.props = None

    def load_xml(self, scene_file):
        import mitsuba
        self.props = mitsuba.xml_to_props(scene_file)

    def get_props_by_name(self, plugin_name):
        for _, props in self.props:
            if props.plugin_name() == plugin_name:
                return props
        return None

@pytest.fixture
def test_resource_resolver():
    return TestResourceResolver()

@pytest.fixture
def mitsuba_scene_parser():
    return MitsubaSceneParser()