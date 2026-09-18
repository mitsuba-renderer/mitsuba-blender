'''
Copies the Python plugins that an exported scene uses next to the scene.

The export directory receives a partial copy of the ``mitsuba_blender.plugins``
package in ``plugins/``: its ``__init__.py``, the modules providing the plugins
of the scene, and the modules these import. The scene imports the package via
``<import filename="plugins/__init__.py"/>``, which registers the plugins of
all copied modules. Exported scenes thereby keep working when the addon's
plugins change.
'''

import ast
import os
import re
import shutil

from ... import plugins

# Subfolder of the export directory receiving the plugins
FOLDER = 'plugins'

_REGISTER = re.compile(r'''\bmi\.register_\w+\(\s*['"]([^'"]+)['"]''')


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def plugin_files():
    '''Map the name of every plugin that the addon registers to its file.'''
    return {name: path for path in plugins.module_files()
            for name in _REGISTER.findall(_read(path))}


def _add_with_imports(path, files):
    '''Add ``path`` and the modules it imports relatively to ``files``.'''
    if path in files:
        return
    files.add(path)
    for node in ast.walk(ast.parse(_read(path))):
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
            module = os.path.join(os.path.dirname(path), *node.module.split('.'))
            _add_with_imports(module + '.py', files)


def bundle_plugins(state, directory):
    '''
    Copy the plugin modules that the parsed scene ``state`` uses to
    ``directory/plugins`` and make the scene import them. An existing
    ``plugins`` folder is replaced.
    '''
    folder = os.path.join(directory, FOLDER)
    shutil.rmtree(folder, ignore_errors=True)

    registry = plugin_files()
    files = set()
    for node in state.nodes:
        path = registry.get(node.props.plugin_name())
        if path is not None:
            _add_with_imports(path, files)
    if not files:
        return

    for path in files | {os.path.join(plugins.PLUGINS_DIR, '__init__.py')}:
        target = os.path.join(folder, os.path.relpath(path, plugins.PLUGINS_DIR))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(path, target)
    state.imports += [f'{FOLDER}/__init__.py']
