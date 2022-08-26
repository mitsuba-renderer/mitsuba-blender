import bpy
from bpy.utils import register_class, unregister_class
from . import (
    transform2d
)

classes = (
    transform2d.MitsubaNode2DTransform,
)

def register():
    for cls in classes:
        register_class(cls)

def unregister():
    for cls in classes:
        unregister_class(cls)
