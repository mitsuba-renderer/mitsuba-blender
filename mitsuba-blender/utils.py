import os, sys

def update_python_paths(mitsuba_path):
    '''
    Update Python paths to include Mitsuba build folder
    '''
    # First remove all paths pointing to a Mitsuba folder
    sys.path = [p for p in sys.path if 'mitsuba' not in p]

    # Add Mitsuba python folder to PYTHONPATH
    mitsuba_path = os.path.abspath(mitsuba_path)
    sys.path.insert(0, mitsuba_path)

    if os.name == "nt":
        sys.path.insert(0, os.path.join(mitsuba_path, 'build', 'Debug',   'python'))
        sys.path.insert(0, os.path.join(mitsuba_path, 'build', 'Release', 'python'))
    else:
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

class dotdict(dict):
    '''
    dot.notation access to dictionary attributes
    '''
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__