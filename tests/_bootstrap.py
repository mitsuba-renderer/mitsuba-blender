"""Runs inside headless Blender, launched by tests/run.py.

Executes pytest with the arguments following '--', writes the exit code to
the file named by MI_BLENDER_TEST_RC_FILE, and exits Blender with it.
"""

import os
import sys
from pathlib import Path

# Must be set before mitsuba is first imported anywhere in the process.
os.environ.setdefault('DRJIT_NO_RTLD_DEEPBIND', '1')

# Tells tests/conftest.py that the new harness is running.
os.environ['MI_BLENDER_TEST_HARNESS'] = '1'

REPO_ROOT = Path(__file__).resolve().parent.parent


def main():
    argv = sys.argv
    args = argv[argv.index('--') + 1:] if '--' in argv else []
    os.chdir(REPO_ROOT)

    import pytest
    rc = int(pytest.main(args))

    rc_file = os.environ.get('MI_BLENDER_TEST_RC_FILE')
    if rc_file:
        Path(rc_file).write_text(str(rc))
    sys.exit(rc)


main()
