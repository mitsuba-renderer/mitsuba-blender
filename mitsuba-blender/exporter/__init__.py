import bpy

from . import converter
from . import materials
from . import nodes
from . import geometry
from . import lights
from . import camera
from .. import logging

@bpy.app.handlers.persistent
def clear_image_cache(dummy):
    logging.info('Clear Mitsuba scene exporter image cache before loading the scene.')
    converter.ExportContext.IMAGES_CACHE = {}

def register():
    bpy.app.handlers.load_pre.append(clear_image_cache)

def unregister():
    logging.info('Cleanup Mitsuba scene converter temp directory')
    converter.SceneConverter.TEMP_DIR.cleanup()
    bpy.app.handlers.load_pre.remove(clear_image_cache)
