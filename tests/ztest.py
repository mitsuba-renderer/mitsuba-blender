"""Statistical z-test comparison of two rendered Mitsuba scenes.

The scenes must wrap their integrator in a `moment` integrator so that a
variance estimate is available for the test statistic.
"""

import os

import numpy as np


class MitsubaSceneRenderer:

    def _bitmap_extract(self, bmp, require_variance=True):
        """Extract mean and variance images from moment integrator AOVs."""
        from mitsuba import Bitmap, Struct
        # AOVs from the moment integrator are in XYZ (float32)
        split = bmp.split()
        if len(split) == 1:
            if require_variance:
                raise RuntimeError(
                    'Could not extract variance image from bitmap. '
                    'Did you wrap the integrator into a `moment` integrator?\n{}'.format(bmp))
            b_root = split[0][1]
            if b_root.channel_count() >= 3 and b_root.pixel_format() != Bitmap.PixelFormat.XYZ:
                b_root = b_root.convert(Bitmap.PixelFormat.XYZ, Struct.Type.Float32, False)
            return np.array(b_root, copy=True), None
        else:
            # Check which split contains moments - it may not be the first one after root
            m2_index = 1 if split[1][0].startswith('m2_') else 2
            mean_index = 2 if m2_index == 1 else 1
            img = np.array(split[mean_index][1], copy=False)
            img_m2 = np.array(split[m2_index][1], copy=False)
            return img, img_m2 - img * img

    def render_scene(self, scene_file, **kwargs):
        from mitsuba import load_file

        scene = load_file(scene_file, **kwargs)
        scene.integrator().render(scene, seed=0, develop=False)

        bmp = scene.sensors()[0].film().bitmap(raw=False)
        img, var_img = self._bitmap_extract(bmp)

        return img, var_img


class MitsubaRenderTester:
    def __init__(self, mitsuba_scene_renderer):
        self.scene_renderer = mitsuba_scene_renderer

    def z_test(self, mean, sample_count, reference, reference_var):
        """Implementation of the Z-test statistical test"""
        import drjit as dr
        from drjit.scalar import ArrayXf as Float
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

    def xyz_to_rgb_bmp(self, arr):
        """Convert an XYZ image to RGB"""
        from mitsuba import Bitmap, Struct
        xyz_bmp = Bitmap(arr, Bitmap.PixelFormat.XYZ)
        return xyz_bmp.convert(Bitmap.PixelFormat.RGB, Struct.Type.Float32, False)

    def compare_scenes(self, xml_ref, xml_out, spp, resolution, output_dir, significance_level=0.01):
        from mitsuba import Bitmap

        pixel_count = resolution[0] * resolution[1]
        ref_img, ref_img_var = self.scene_renderer.render_scene(xml_ref, spp=spp, resx=resolution[0], resy=resolution[1])
        img, _ = self.scene_renderer.render_scene(xml_out, spp=spp, resx=resolution[0], resy=resolution[1])

        p_value = self.z_test(img, spp, ref_img, ref_img_var)

        # Apply the Sidak correction term, since we'll be conducting multiple independent
        # hypothesis tests. This accounts for the fact that the probability of a failure
        # increases quickly when several hypothesis tests are run in sequence.
        alpha = 1.0 - (1.0 - significance_level) ** (1.0 / pixel_count)

        success = (p_value > alpha)

        ref_img_bmp = self.xyz_to_rgb_bmp(ref_img)
        img_bmp = self.xyz_to_rgb_bmp(img)
        err_bmp = 0.02 * np.array(img_bmp)
        err_bmp[~success] = 1.0
        err_bmp = Bitmap(err_bmp)

        ref_img_bmp.write(os.path.join(output_dir, 'ref.exr'))
        img_bmp.write(os.path.join(output_dir, 'out.exr'))
        err_bmp.write(os.path.join(output_dir, 'err.exr'))

        return np.count_nonzero(success) / 3 >= 0.9975 * pixel_count
