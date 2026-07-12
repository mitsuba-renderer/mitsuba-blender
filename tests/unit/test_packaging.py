"""Builds the extension zip and installs it into a factory Blender."""

import os
import subprocess
import textwrap

import bpy
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.realpath(__file__))))

INSTALL_CHECK_SCRIPT = textwrap.dedent('''
    import sys
    import bpy

    zip_path = sys.argv[sys.argv.index('--') + 1]
    result = bpy.ops.extensions.package_install_files(
        filepath=zip_path, repo='user_default', enable_on_install=True)
    assert result == {'FINISHED'}, result
    assert 'bl_ext.user_default.mitsuba_blender' in bpy.context.preferences.addons

    engines = {getattr(cls, 'bl_idname', None)
               for cls in bpy.types.RenderEngine.__subclasses__()}
    assert 'MITSUBA' in engines, engines
    print('MI_PACKAGING_OK')
''')


@pytest.mark.packaging
def test_extension_build_and_install(tmp_path):
    blender = bpy.app.binary_path
    zip_path = tmp_path / 'mitsuba_blender.zip'

    build = subprocess.run(
        [blender, '--command', 'extension', 'build',
         '--source-dir', os.path.join(REPO_ROOT, 'mitsuba_blender'),
         '--output-filepath', str(zip_path)],
        capture_output=True, text=True, timeout=300)
    assert build.returncode == 0, build.stdout + build.stderr
    assert zip_path.is_file()

    script = tmp_path / 'install_check.py'
    script.write_text(INSTALL_CHECK_SCRIPT)

    # Isolated user resources keep the install out of the developer's real
    # extension repository.
    env = os.environ.copy()
    env['BLENDER_USER_RESOURCES'] = str(tmp_path / 'user_resources')
    env['DRJIT_NO_RTLD_DEEPBIND'] = '1'

    install = subprocess.run(
        [blender, '-b', '--factory-startup', '--python-exit-code', '1',
         '--python', str(script), '--', str(zip_path)],
        capture_output=True, text=True, timeout=300, env=env)
    assert install.returncode == 0, install.stdout + install.stderr
    assert 'MI_PACKAGING_OK' in install.stdout
