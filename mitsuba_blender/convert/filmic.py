'''Blender's Filmic view transform: the contrast of its looks, and the
conversion of view-level curve mappings into the float32 EXR table read by
the ``filmic`` post-processing plugin.'''

import os

import numpy as np

# Contrast of each look of the Filmic view: the first number in the name of
# the look's curve table (e.g. filmic_to_0-70_1-03.spi1d). The fitted toe
# exponent of each curve matches it to within a few percent, which is why
# the plugin treats it as the contrast. "Medium Contrast" is the view's
# base curve.
LOOK_CONTRAST = {
    'Very Low Contrast': 0.35,
    'Low Contrast': 0.48,
    'Medium Low Contrast': 0.60,
    'Medium Contrast': 0.70,
    'Medium High Contrast': 0.85,
    'High Contrast': 0.99,
    'Very High Contrast': 1.20,
}

VIEW_CURVES_FILE = 'view_curves.exr'

# Resolution of Blender's curve mapping tables (CM_TABLE in colortools.cc)
CURVE_TABLE_SIZE = 256


def write_table(path, table, domain=None):
    '''Write a table of shape (rows, columns) or (rows, columns, channels)
    as a float32 EXR image, with the input domain as metadata.'''
    import mitsuba as mi
    bitmap = mi.Bitmap(np.ascontiguousarray(table, dtype=np.float32))
    if domain is not None:
        bitmap.metadata()['domain_min'] = float(domain[0])
        bitmap.metadata()['domain_max'] = float(domain[1])
    bitmap.write(path)


def export_view_curves(folder, curve_mapping, prefix=''):
    '''Write the view-level curve mapping as the per-channel tables that
    Blender evaluates: the black/white levels rescale the input, then the
    channel's curve and then the combined curve are applied (see
    BKE_curvemapping_premultiply in colortools.cc). The samples cover
    Blender's table range plus one step on each side so the plugin's
    linear extrapolation matches Blender's. Returns the file name.'''
    cm = curve_mapping
    cm.initialize()
    black = np.array(cm.black_level, dtype=np.float64)
    bwmul = 1.0 / np.maximum(np.array(cm.white_level, dtype=np.float64) - black, 1e-5)
    x0, x1 = cm.clip_min_x, cm.clip_max_x
    dx = (x1 - x0) / CURVE_TABLE_SIZE
    # Input range that covers the table of every channel
    lo = float(np.min(black + (x0 - dx) / bwmul))
    hi = float(np.max(black + (x1 + dx) / bwmul))
    xs = np.linspace(lo, hi, CURVE_TABLE_SIZE + 3)

    combined = cm.curves[3]
    table = np.empty((xs.shape[0], 3))
    for c in range(3):
        curve = cm.curves[c]
        table[:, c] = [cm.evaluate(combined, cm.evaluate(curve, float((x - black[c]) * bwmul[c])))
                       for x in xs]
    write_table(os.path.join(folder, VIEW_CURVES_FILE), table[None], (lo, hi))
    return prefix + VIEW_CURVES_FILE
