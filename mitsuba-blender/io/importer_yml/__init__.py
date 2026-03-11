"""YAML-based scene importer for Mitsuba-Blender."""
from . import utils
import bpy


OPTIMIZABLE_MATERIALS = {} # Global dict to store optimizable materials by name?
def build_new_scene(init_scene, config_path="scene_config.yml"):
    """Assemble blender scene from config file."""
    bpy.context.window.scene = init_scene
    utils.reset_viewport_settings(init_scene)

    cfg = utils.load_config(config_path)
    utils.setup_render(init_scene, cfg)
    utils.setup_cameras(init_scene, cfg)
    utils.setup_lights(init_scene, cfg)
    utils.setup_background(init_scene, cfg)
    utils.setup_objects(init_scene, cfg)
    utils.setup_fog(init_scene, cfg)
    return
