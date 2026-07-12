#!/usr/bin/env python3
"""Builds distributable extension zips with bundled Mitsuba wheels.

Copies the addon into a staging directory, downloads the mitsuba and drjit
wheels for every supported platform, lists them in the manifest, and invokes
Blender's extension builder with --split-platforms to produce one zip per
platform in the output directory.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MITSUBA_VERSION = '3.9.0'

# Blender bundles Python 3.11 up to release 5.0 and Python 3.13 from 5.1
# on. Wheels for both are listed in the manifest; at install time Blender
# deploys the ones whose tag matches its own Python.
PYTHON_VERSIONS = ['3.11', '3.13']

# Blender extension platforms and the matching pip platform tags. Mitsuba
# ships no macos-x64 wheels, so that platform is not part of the release.
PLATFORMS = {
    'linux-x64': 'manylinux_2_28_x86_64',
    'windows-x64': 'win_amd64',
    'macos-arm64': 'macosx_11_0_arm64',
}


def download_wheels(wheels_dir):
    wheels_dir.mkdir(parents=True, exist_ok=True)
    for platform_tag in PLATFORMS.values():
        for python_version in PYTHON_VERSIONS:
            subprocess.check_call([
                sys.executable, '-m', 'pip', 'download',
                f'mitsuba=={MITSUBA_VERSION}',
                '--dest', str(wheels_dir),
                '--only-binary=:all:',
                '--implementation', 'cp',
                '--python-version', python_version,
                '--platform', platform_tag,
            ])
    return [path.name for path in wheels_dir.glob('*.whl')]


def patch_manifest(manifest_path, wheel_names):
    wheels = ',\n'.join(f'    "./wheels/{name}"' for name in sorted(wheel_names))
    platforms = ', '.join(f'"{name}"' for name in PLATFORMS)
    replacement = (f'platforms = [{platforms}]\n'
                   f'wheels = [\n{wheels},\n]')
    text, count = re.subn(r'wheels = \[\]', replacement,
                          manifest_path.read_text())
    if count != 1:
        sys.exit('error: expected exactly one "wheels = []" entry in the manifest')
    manifest_path.write_text(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--blender', default=os.environ.get('BLENDER'),
                        help='Blender executable used to build the extension '
                             '(defaults to the BLENDER environment variable)')
    parser.add_argument('--output-dir', default='dist',
                        help='directory receiving the built zips')
    args = parser.parse_args()
    if not args.blender:
        sys.exit('error: pass --blender or set the BLENDER environment variable')

    repo_root = Path(__file__).resolve().parent.parent
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as staging:
        source_dir = Path(staging) / 'mitsuba_blender'
        shutil.copytree(repo_root / 'mitsuba_blender', source_dir,
                        ignore=shutil.ignore_patterns('__pycache__'))
        wheel_names = download_wheels(source_dir / 'wheels')
        patch_manifest(source_dir / 'blender_manifest.toml', wheel_names)
        subprocess.check_call([
            args.blender, '--command', 'extension', 'build',
            '--source-dir', str(source_dir),
            '--output-dir', str(output_dir),
            '--split-platforms',
        ])

    print('Built:')
    for zip_path in sorted(output_dir.glob('*.zip')):
        print(f'  {zip_path}')


if __name__ == '__main__':
    main()
