import bpy
from .final import MitsubaRenderEngine

def register():
    bpy.utils.register_class(MitsubaRenderEngine)

def unregister():
    bpy.utils.unregister_class(MitsubaRenderEngine)
