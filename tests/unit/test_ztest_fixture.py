"""Regression test for the legacy z-test fixture in tests/fixtures.

The mean image and the second moment must come from their respective splits
of the moment integrator output. A constant emitter of radiance 0.5 has mean
0.5 and second moment 0.25 with zero variance, which tells the two apart.
"""

import numpy as np

from fixtures import MitsubaSceneRenderer


def test_bitmap_extract_moment_splits():
    import mitsuba as mi
    mi.set_variant('scalar_rgb')

    scene = mi.load_dict({
        'type': 'scene',
        'integrator': {
            'type': 'moment',
            'nested': {'type': 'path', 'max_depth': 2},
        },
        'sensor': {
            'type': 'perspective',
            'film': {
                'type': 'hdrfilm',
                'width': 8,
                'height': 8,
                'rfilter': {'type': 'box'},
            },
            'sampler': {'type': 'independent', 'sample_count': 4},
        },
        'emitter': {'type': 'constant', 'radiance': 0.5},
    })
    scene.integrator().render(scene, seed=0, develop=False)
    bmp = scene.sensors()[0].film().bitmap(raw=False)

    img, var_img = MitsubaSceneRenderer()._bitmap_extract(bmp)

    # The mean image is in XYZ; luminance (Y) of linear rgb (0.5, 0.5, 0.5)
    # is exactly 0.5. The buggy version returned the second moment (0.25).
    assert np.allclose(img[:, :, 1], 0.5, atol=1e-3)
    # A constant image has zero sample variance.
    assert np.allclose(var_img, 0.0, atol=1e-3)
