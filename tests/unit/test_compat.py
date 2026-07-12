"""compat.py is the only module allowed to touch version-dependent API."""

import os

REPO_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.realpath(__file__))))
ADDON_DIR = os.path.join(REPO_ROOT, 'mitsuba_blender')


def _offenders(needle):
    offenders = []
    for dirpath, _, filenames in os.walk(ADDON_DIR):
        for filename in filenames:
            if not filename.endswith('.py'):
                continue
            path = os.path.join(dirpath, filename)
            if os.path.relpath(path, ADDON_DIR) == 'compat.py':
                continue
            with open(path) as f:
                if needle in f.read():
                    offenders.append(os.path.relpath(path, ADDON_DIR))
    return offenders


def test_version_checks_only_in_compat():
    assert _offenders('bpy.app.version') == []


def test_use_nodes_only_in_compat():
    # use_nodes is deprecated in Blender 5.0 and removed in 6.0; go
    # through compat.uses_nodes / compat.ensure_node_tree instead
    assert _offenders('use_nodes') == []
