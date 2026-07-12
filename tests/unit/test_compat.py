"""compat.py is the only module allowed to inspect bpy.app.version."""

import os

REPO_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.realpath(__file__))))
ADDON_DIR = os.path.join(REPO_ROOT, 'mitsuba_blender')


def test_version_checks_only_in_compat():
    offenders = []
    for dirpath, _, filenames in os.walk(ADDON_DIR):
        for filename in filenames:
            if not filename.endswith('.py'):
                continue
            path = os.path.join(dirpath, filename)
            if os.path.relpath(path, ADDON_DIR) == 'compat.py':
                continue
            with open(path) as f:
                if 'bpy.app.version' in f.read():
                    offenders.append(os.path.relpath(path, ADDON_DIR))
    assert offenders == []
