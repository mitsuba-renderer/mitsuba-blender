import os, sys, subprocess, re
from . import MI_VERSION

def get_addon_preferences(context):
    return context.preferences.addons[__package__].preferences

def ensure_pip():
    result = subprocess.run([sys.executable, '-m', 'ensurepip'], capture_output=True)
    return result.returncode == 0

def get_pip_mi_version():
    '''
    Manually check by querying pip the version of the new installation of mitsuba, if it exists
    This is useful to run checks before requiring a blender restart.
    '''
    result = subprocess.run([sys.executable, '-m', 'pip', 'show', 'mitsuba'], capture_output=True, text=True)
    if result.returncode == 0:
        regex_match = re.search(r'Version:\s*(\d+\.\d+\.\d+)', result.stdout, flags=re.MULTILINE)
        return regex_match.group(1)
    return None # Mitsuba was not found

def update_python_paths(mitsuba_path):
    '''
    Update Python paths to include Mitsuba build folder
    '''
    # First remove all paths pointing to a Mitsuba folder
    sys.path = [p for p in sys.path if 'mitsuba' not in p]

    # Add Mitsuba python folder to PYTHONPATH
    mitsuba_path = os.path.abspath(mitsuba_path)
    sys.path.insert(0, mitsuba_path)
    sys.path.insert(0, os.path.join(mitsuba_path, 'python'))

def find_mitsuba():
    '''
    Find Mitsuba path by importing Mitsuba on the system Python (python or python3)
    '''
    def f(executable):
        import subprocess
        cmd = [executable, '-c', 'import mitsuba; print(mitsuba.__path__[0])']
        return subprocess.run(cmd, capture_output=True, text=True).stdout[:-5]
    try:
        return f('python')
    except:
        try:
            return f('python3')
        except:
            return ''

def check_mitsuba_version(version_str):
    '''
    Given a mitsuba version string, check it against the minimum required version.
    '''
    v = [int(v) for v in version_str.split('.')]
    valid_version = False
    if v[0] > MI_VERSION[0]:
        valid_version = True
    elif v[0] == MI_VERSION[0]:
        if v[1] > MI_VERSION[1]:
            valid_version = True
        elif v[1] == MI_VERSION[1]:
            if v[2] >= MI_VERSION[2]:
                valid_version = True
    return valid_version

class dotdict(dict):
    '''
    dot.notation access to dictionary attributes
    '''
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__
