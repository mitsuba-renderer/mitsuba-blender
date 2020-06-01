bl_info = {
    "name": "Mitsuba2-Blender",
    "author": "Baptiste Nicolet",
    "version": (0, 1),
    "blender": (2, 80, 0),
    "category": "Exporter",
    "location": "File > Export > Mitsuba 2",
    "description": "Mitsuba2 export for Blender",
    "warning": "alpha0",
    "support": "TESTING"
}

import bpy
import os
import sys
from bpy.props import StringProperty
from bpy.types import AddonPreferences
from . import export, engine
#from export import MitsubaFileExport, MitsubaPrefs

def get_mitsuba_path():
    # Try to get the path to the Mitsuba 2 root folder
    tokens = os.getenv('MITSUBA_DIR')
    if tokens:
        for token in tokens.split(':'):
            path = os.path.join(token, 'build')
            if os.path.isdir(path):
                return path
    return ""

class MitsubaPrefs(AddonPreferences):

    bl_idname = __name__

    mitsuba_path: StringProperty(
        name="Build Path",
        description="Path to the Mitsuba 2 build directory",
        subtype='DIR_PATH',
        default=get_mitsuba_path()
        )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "mitsuba_path")

def register():
    bpy.utils.register_class(MitsubaPrefs)
    export.register()
    engine.register()

def unregister():
    bpy.utils.unregister_class(MitsubaPrefs)
    export.unregister()
    engine.unregister()

if __name__ == '__main__':
    register()
