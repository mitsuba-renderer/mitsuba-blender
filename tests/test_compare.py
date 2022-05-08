import os
import sys
import numpy as np

import bpy

from utils import mi_scene_utils

def z_test(mean, sample_count, reference, reference_var):
    import drjit as dr
    from drjit.scalar import ArrayXf as Float
    """Implementation of the Z-test statistical test"""
    # Sanitize the variance images
    reference_var = np.maximum(reference_var, 1e-4)

    # Compute Z statistic
    z_stat = np.abs(mean - reference) * np.sqrt(sample_count / reference_var)

    # Cumulative distribution function of the standard normal distribution
    def stdnormal_cdf(x):
        shape = x.shape
        cdf = (1.0 - dr.erf(-Float(x.flatten()) / dr.sqrt(2.0))) * 0.5
        return np.array(cdf).reshape(shape)

    # Compute p-value
    p_value = 2.0 * (1.0 - stdnormal_cdf(z_stat))

    return p_value

def test_round_trip():
    from mitsuba import Bitmap

    res = (1280, 720)
    sample_budget = int(2e6)
    pixel_count = res[0]*res[1]
    spp = sample_budget // pixel_count

    significance_level = 0.01

    cwd = os.getcwd()

    test_scene_dir = os.path.join(cwd, 'tests/res/scenes')
    test_scene_file = os.path.join(test_scene_dir, 'test1.xml')

    test_scene_out_dir = os.path.join(test_scene_dir, 'out')
    if not os.path.exists(test_scene_out_dir):
        os.mkdir(test_scene_out_dir)

    test_scene_out_file = os.path.join(test_scene_out_dir, 'test1.xml')

    # Render normal scene
    ref_img, ref_img_var = mi_scene_utils.render_scene(test_scene_file, spp=spp, res=res)

    assert bpy.ops.import_scene.mitsuba2(filepath=test_scene_file) == {'FINISHED'}
    assert bpy.ops.export_scene.mitsuba2(filepath=test_scene_out_file, ignore_background=True) == {'FINISHED'}

    img, _ = mi_scene_utils.render_scene(test_scene_out_file, spp=spp, res=res)

    p_value = z_test(img, spp, ref_img, ref_img_var)

    # Apply the Sidak correction term, since we'll be conducting multiple independent
    # hypothesis tests. This accounts for the fact that the probability of a failure
    # increases quickly when several hypothesis tests are run in sequence.
    alpha = 1.0 - (1.0 - significance_level) ** (1.0 / pixel_count)

    success = (p_value > alpha)

    ref_img_bmp = mi_scene_utils.xyz_to_rgb_bmp(ref_img)
    img_bmp = mi_scene_utils.xyz_to_rgb_bmp(img)
    err_bmp = 0.02 * np.array(img_bmp)
    err_bmp[~success] = 1.0
    err_bmp = Bitmap(err_bmp)

    ref_img_bmp.write(os.path.join(test_scene_out_dir, 'ref.exr'))
    img_bmp.write(os.path.join(test_scene_out_dir, 'out.exr'))
    err_bmp.write(os.path.join(test_scene_out_dir, 'err.exr'))

    assert np.count_nonzero(success) / 3 >= 0.9975 * pixel_count
