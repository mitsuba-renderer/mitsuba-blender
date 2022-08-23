import os
import numpy as np

def _bitmap_extract(bmp, require_variance=True):
    from mitsuba import Bitmap, Struct
    """Extract different channels from moment integrator AOVs"""
    # AVOs from the moment integrator are in XYZ (float32)
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
        img = np.array(split[1][1], copy=False)
        img_m2 = np.array(split[2][1], copy=False)
        return img, img_m2 - img * img

def xyz_to_rgb_bmp(arr):
    """Convert an XYZ image to RGB"""
    from mitsuba import Bitmap, Struct
    xyz_bmp = Bitmap(arr, Bitmap.PixelFormat.XYZ)
    return xyz_bmp.convert(Bitmap.PixelFormat.RGB, Struct.Type.Float32, False)

def render_scene(scene_file, spp, res):
    from mitsuba import load_file

    scene = load_file(scene_file, spp=spp, resx=res[0], resy=res[1])
    scene.integrator().render(scene, seed=0, develop=False)

    bmp = scene.sensors()[0].film().bitmap(raw=False)
    img, var_img = _bitmap_extract(bmp)

    return img, var_img
