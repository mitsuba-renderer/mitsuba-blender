#!/usr/bin/env python3
"""Host-side test launcher.

Runs the pytest suite inside a headless Blender found via the BLENDER
environment variable and propagates pytest's exit code. See tests/README.md.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_TEST_DIRS = ('tests/unit', 'tests/roundtrip', 'tests/golden')


def find_blender():
    blender = os.environ.get('BLENDER')
    if not blender:
        sys.exit('error: set the BLENDER environment variable to the Blender '
                 'executable, e.g. BLENDER=/path/to/blender-4.2/blender')
    if not (os.path.isfile(blender) and os.access(blender, os.X_OK)):
        sys.exit(f'error: BLENDER={blender} is not an executable file')
    return blender


def build_pytest_args(argv):
    args = list(argv)
    run_all = '--all' in args
    if run_all:
        args.remove('--all')

    # Positional arguments select test files; without any, run every test
    # directory that exists.
    if not any(not a.startswith('-') for a in args):
        args += [d for d in DEFAULT_TEST_DIRS if (REPO_ROOT / d).is_dir()]

    # Skip slow and packaging tests unless the caller opts in.
    if not run_all and '-m' not in args:
        args += ['-m', 'not slow and not packaging']
    return args


def pytest_tail(output, max_lines=40):
    """Extracts the tail of the pytest report from Blender's noisy output."""
    lines = output.splitlines()
    start = 0
    for i, line in enumerate(lines):
        if 'test session starts' in line:
            start = i
    block = lines[start:]

    # Prefer the part from the failure/summary sections onwards.
    for marker in ('short test summary info', 'FAILURES', 'ERRORS'):
        for i, line in enumerate(block):
            if marker in line:
                return block[i:][-max_lines:]
    return block[-max_lines:]


def main(argv):
    blender = find_blender()
    pytest_args = build_pytest_args(argv)

    env = os.environ.copy()
    env['DRJIT_NO_RTLD_DEEPBIND'] = '1'
    # Point Blender's user config/scripts/extensions at a throwaway directory
    # so the conftest addon install cannot touch the developer's real profile.
    user_resources = tempfile.mkdtemp(prefix='mi-blender-test-home-')
    env['BLENDER_USER_RESOURCES'] = user_resources
    rc_fd, rc_path = tempfile.mkstemp(prefix='mi-blender-test-rc-')
    os.close(rc_fd)
    os.remove(rc_path)
    env['MI_BLENDER_TEST_RC_FILE'] = rc_path

    cmd = [blender, '-b', '--factory-startup',
           '--python', str(REPO_ROOT / 'tests' / '_bootstrap.py'),
           '--', *pytest_args]
    print('Running:', ' '.join(cmd), flush=True)

    proc = subprocess.run(cmd, cwd=REPO_ROOT, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, errors='replace')

    log_fd, log_path = tempfile.mkstemp(prefix='mi-blender-test-',
                                        suffix='.log', text=True)
    with os.fdopen(log_fd, 'w') as f:
        f.write(proc.stdout)

    try:
        rc = int(Path(rc_path).read_text().strip())
        crashed = False
    except (FileNotFoundError, ValueError):
        rc = proc.returncode if proc.returncode != 0 else 1
        crashed = True
    finally:
        Path(rc_path).unlink(missing_ok=True)
        shutil.rmtree(user_resources, ignore_errors=True)

    print()
    for line in pytest_tail(proc.stdout):
        print(line)
    print()
    print(f'Full Blender output: {log_path}')
    if crashed:
        print(f'FAIL: Blender exited (code {proc.returncode}) before pytest '
              'could report a result')
    elif rc == 0:
        print('PASS')
    else:
        print(f'FAIL (pytest exit code {rc})')
    return rc


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
