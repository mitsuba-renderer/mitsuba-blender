import mitsuba as mi
mi.set_variant('cuda_ad_rgb')

import sys
import utils.compare_utils as utils
import numpy as np
import matplotlib.image as img
import os 

def main(ref_scene, samples):
    scene = mi.load_file(ref_scene)

    renders = np.empty(shape=(samples), dtype=np.ndarray)
    for i in range(samples):
        ref_render = f'render{i}.png'
        utils.convert_png(mi.Bitmap(mi.render(scene, seed=mi.UInt32(i), spp=128))).write(ref_render)
        renders[i] = np.asarray(img.imread(ref_render))

    pairs = np.array(np.meshgrid(renders, renders, indexing='xy')).T.reshape((-1, 2))
    errors = []
    for p in pairs:
        if (p[0] != p[1]).any():
            err, _, _ = utils.mse(p[0], p[1], gray_scale=False)
            errors.append(err)
    
    avg_err = np.asarray(errors).sum() / len(errors)
    print(f'average error between two visually identical image: {avg_err}')
    os.system('rm render*')


if __name__ == '__main__':
    ref_scene = sys.argv[1]
    samples = int(sys.argv[2])
    main(ref_scene, samples)