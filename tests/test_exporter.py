import mitsuba as mi
mi.set_variant("scalar_rgb")
import numpy as np
import utils.compare_utils as util
import matplotlib.image as img
import pytest

from fixtures import *

@pytest.mark.parametrize(
    "shader_node", 
    [
        'glass',
        'glass_r0.5',
        'glass_r1',
        'diffuse',
        'diffuse_r0.5',
        'diffuse_r1',
        'emission',
        'emission_str5',
        'emission_str10',
        'glossy_r0',
        'glossy_r0.5',
        'glossy_r1',
    ]
) #TODO add every material
@pytest.mark.parametrize("bl_scene", ['bunny.blend'])
def test_export(resource_resolver, blender_exporter, shader_node, bl_scene):
    resolution = (1280, 720)

    # Setup blender scene
    blender_exporter.setup_blender(bl_scene, resolution=resolution)
    
    # Set blender material
    assert blender_exporter.set_material(shader_node)
    
    # Render and export blender scene
    ref_mi_scene = f'{resource_resolver.get_scenes_path()}/exported/{shader_node}.xml'
    ref_bl_render = f'{resource_resolver.get_renders_path()}/blender/{shader_node}.png' 
    blender_exporter.render_and_export(ref_bl_render, ref_mi_scene)

    # Render exported scene in mitsuba and save result
    mi_img = mi.render(mi.load_file(ref_mi_scene, resx=resolution[0], resy=resolution[1]))
    ref_mi_render = f'{resource_resolver.get_renders_path()}/mitsuba/{shader_node}.png' 
    mi_img = util.convert_png(mi.Bitmap(mi_img))
    mi_img.write(ref_mi_render)

    # Compare renders
    bl_img = np.asarray(img.imread(ref_bl_render))
    mi_img = np.asarray(img.imread(ref_mi_render))
    err, var, diff = util.mse(mi_img, bl_img)

    # Save diff
    ref_diff = f"{resource_resolver.get_out_path()}/tests/{shader_node}_diff.png"
    img.imsave(ref_diff, diff, cmap='gray')

    assert err < 0.000306 and False,  f"Error is too big (err = {err}), should be less than 0.000306" 