"""Exported scenes ship the Python plugins they use in plugins/ and import
them, so that they load without the addon."""

import os
import subprocess
import sys

import bpy
import pytest


@pytest.fixture(scope='session')
def bundle(mi_addon):
    return sys.modules[mi_addon].io.exporter.plugin_bundle


@pytest.fixture(scope='session')
def plugins(mi_addon):
    return sys.modules[mi_addon].plugins


def test_plugin_files(bundle, plugins):
    files = bundle.plugin_files()
    assert set(files.values()) == set(plugins.module_files())
    assert files['cycles_lights'] == files['cycles_lights_emitter']


def test_bundle_copies_used_plugins(bundle, plugins, tmp_path):
    import mitsuba as mi
    mi.set_variant('scalar_rgb')
    state = mi.parser.parse_dict(mi.parser.ParserConfig('scalar_rgb'),
                                 {'type': 'scene', 'tex': {'type': 'tex_noise'}})
    bundle.bundle_plugins(state, str(tmp_path))
    assert state.imports == ['plugins/__init__.py']
    files = sorted(os.path.relpath(os.path.join(root, name), tmp_path / 'plugins')
                   for root, _, names in os.walk(tmp_path / 'plugins') for name in names)
    assert files == ['__init__.py', os.path.join('textures', 'tex_noise.py')]

    # The bundled package registers the plugin
    try:
        mi.load_dict({'type': 'scene', 'ext': {'type': 'import', 'filename':
                      str(tmp_path / 'plugins' / '__init__.py')}})
        texture = mi.load_dict({'type': 'tex_noise'})
        assert type(texture).__module__.startswith('_mitsuba_import_')
    finally:
        plugins.register_plugins()


def _export(mi_addon, directory):
    from bl_ext.user_default.mitsuba_blender.io.exporter import SceneConverter
    import mitsuba as mi
    mi.set_variant('scalar_rgb')
    converter = SceneConverter(render=False)
    converter.export_ctx.directory = str(directory)
    converter.scene_to_dict(bpy.context.evaluated_depsgraph_get())
    filename = os.path.join(str(directory), 'scene.xml')
    converter.dict_to_xml(filename)
    return filename


def test_export_bundles_used_plugins(mi_addon, fresh_scene, tmp_path):
    fresh_scene.view_settings.view_transform = 'Filmic'
    fresh_scene.render.resolution_percentage = 4
    light = bpy.data.objects['Light'].data
    assert light.type == 'POINT' and light.shadow_soft_size > 0

    (tmp_path / 'plugins').mkdir()
    (tmp_path / 'plugins' / 'stale.py').write_text('raise RuntimeError\n')

    filename = _export(mi_addon, tmp_path)
    assert sorted(os.listdir(tmp_path / 'plugins')) == ['__init__.py', 'postprocess', 'shapes']
    assert os.listdir(tmp_path / 'plugins' / 'postprocess') == ['filmic.py']
    assert os.listdir(tmp_path / 'plugins' / 'shapes') == ['cycles_lights.py']

    lines = [line.strip() for line in open(filename)]
    assert lines[1] == '<import filename="plugins/__init__.py"/>'
    assert lines.count('<import filename="plugins/__init__.py"/>') == 1

    # A fresh interpreter renders the export without the addon
    import mitsuba as mi
    variant = next((v for v in ('llvm_ad_rgb', 'cuda_ad_rgb') if v in mi.variants()),
                   'scalar_rgb')
    script = f'''
import sys
import mitsuba as mi
mi.set_variant({variant!r})
scene = mi.load_file({filename!r})
stage = scene.sensors()[0].film().postprocess()[0]
assert type(stage).__module__.startswith('_mitsuba_import_'), type(stage).__module__
assert not any('mitsuba_blender' in name or name == 'plugins' for name in sys.modules)
image = mi.render(scene, spp=1)
assert image.shape[:2] == (43, 76), image.shape
print('RENDERED')
'''
    mitsuba_root = os.path.dirname(os.path.dirname(os.path.abspath(mi.__file__)))
    env = dict(os.environ, PYTHONPATH=mitsuba_root, PYTHONNOUSERSITE='1')
    result = subprocess.run([sys.executable, '-c', script], env=env,
                            capture_output=True, text=True, cwd=str(tmp_path))
    assert 'RENDERED' in result.stdout, result.stdout + result.stderr


def test_export_without_python_plugins(mi_addon, fresh_scene, tmp_path):
    fresh_scene.view_settings.view_transform = 'Filmic'
    bpy.data.objects.remove(bpy.data.objects['Light'])
    from bl_ext.user_default.mitsuba_blender.io.exporter import SceneConverter
    converter = SceneConverter(render=False)
    converter.export_ctx.directory = str(tmp_path)
    converter.export_ctx.bake_display_transform = False
    converter.scene_to_dict(bpy.context.evaluated_depsgraph_get())
    converter.dict_to_xml(str(tmp_path / 'scene.xml'))
    assert not (tmp_path / 'plugins').exists()
    assert '<import' not in (tmp_path / 'scene.xml').read_text()
