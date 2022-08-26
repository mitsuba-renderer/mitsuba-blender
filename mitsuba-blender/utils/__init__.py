import bpy

import sys
import subprocess

#####################
##  PIP Utilities  ##
#####################

def pip_ensure():
    ''' Ensure that pip is available in the executing Python environment. '''
    result = subprocess.run([sys.executable, '-m', 'ensurepip'], capture_output=True)
    return result.returncode == 0

def pip_has_package(package: str):
    ''' Check if the executing Python environment has a specified package. '''
    result = subprocess.run([sys.executable, '-m', 'pip', 'show', package], capture_output=True)
    return result.returncode == 0

def pip_install_package(package: str, version: str = None):
    ''' Install a specified package in the executing Python environment. '''
    if version is None:
        result = subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', package], capture_output=True)
    else:
        result = subprocess.run([sys.executable, '-m', 'pip', 'install', '--force-reinstall', f'{package}=={version}'], capture_output=True)
    return result.returncode == 0

def pip_package_version(package: str):
    ''' Get the version string of a specific pip package. '''
    result = subprocess.run([sys.executable, '-m', 'pip', 'list'], capture_output=True)
    if result.returncode != 0:
        return None

    output_str = result.stdout.decode('utf-8')
    lines = output_str.splitlines(keepends=False)
    for line in lines:
        parts = line.split()
        if len(parts) >= 2 and parts[0] == package:
            return parts[1]
    return None
