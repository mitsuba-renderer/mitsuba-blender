import bpy

from .final import MitsubaRenderEngine, clear_texture_cache


def register():
    bpy.utils.register_class(MitsubaRenderEngine)


def unregister():
    bpy.utils.unregister_class(MitsubaRenderEngine)
    clear_texture_cache()

