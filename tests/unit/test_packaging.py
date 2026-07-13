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


@pytest.mark.packaging
def test_release_build_bundles_and_installs(tmp_path):
    '''Exercises release/build_extension.py end to end: wheels downloaded and
    listed in the manifest, per-platform zips built, and the linux zip
    installable into an isolated factory Blender.'''
    import sys
    import zipfile

    dist = tmp_path / 'dist'
    build = subprocess.run(
        [sys.executable, os.path.join(REPO_ROOT, 'release', 'build_extension.py'),
         '--blender', bpy.app.binary_path, '--output-dir', str(dist)],
        capture_output=True, text=True, timeout=900)
    if build.returncode != 0:
        output = build.stdout + build.stderr
        network_errors = ('Connection', 'Temporary failure', 'ReadTimeout',
                          'No matching distribution', 'proxy')
        if any(marker in output for marker in network_errors):
            pytest.skip('wheel download failed (offline?)')
        assert build.returncode == 0, output

    zips = sorted(dist.glob('*linux_x64*.zip'))
    assert zips, f'no linux zip in {list(dist.iterdir())}'
    with zipfile.ZipFile(zips[0]) as zf:
        names = zf.namelist()
        wheels = [n for n in names if n.startswith('wheels/') and n.endswith('.whl')]
        assert any('mitsuba' in w for w in wheels), wheels
        assert any('drjit' in w for w in wheels), wheels
        manifest = zf.read('blender_manifest.toml').decode()
        assert 'wheels = [' in manifest and '.whl' in manifest

    script = tmp_path / 'install_check.py'
    script.write_text(INSTALL_CHECK_SCRIPT)
    env = os.environ.copy()
    env['BLENDER_USER_RESOURCES'] = str(tmp_path / 'user_resources')
    env['DRJIT_NO_RTLD_DEEPBIND'] = '1'
    install = subprocess.run(
        [bpy.app.binary_path, '-b', '--factory-startup', '--python-exit-code', '1',
         '--python', str(script), '--', str(zips[0])],
        capture_output=True, text=True, timeout=300, env=env)
    assert install.returncode == 0, install.stdout + install.stderr
    assert 'MI_PACKAGING_OK' in install.stdout
