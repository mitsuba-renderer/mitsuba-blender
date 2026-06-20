import numpy as np
import pytest
import os
from utils.compare_utils import mse, mae
import matplotlib.image as img
from fixtures import *

@pytest.mark.parametrize("mi_simple, tests_out", [("renders/tests/mi_simple.png", "out/tests")])
def test_same_renders(resource_resolver, mi_simple, tests_out):
    # Clear output directory
    ref_tests_out = resource_resolver.get_absolute_resource_path(tests_out)

    r = img.imread(resource_resolver.get_absolute_resource_path(mi_simple))
    r2 = r
    err, v, diff = mae(r, r2)
    assert err == 0, f"MAE of a render with itself should be 0 but got {err}"
    assert v == 0, f"Standard deviation of a render with itself should be 0 but got {err}"
    img.imsave(os.path.join(ref_tests_out, 'mae_same_diff.png'), diff, cmap='gray')
    
    err, v, diff = mse(r, r2)
    assert err == 0, f"MSE of a render with itself should be 0 but got {err}"
    assert v == 0, f"Standard deviation of a render with itself should be 0 but got {err}"
    img.imsave(os.path.join(ref_tests_out, "mse_same_diff.png"), diff, cmap='gray')

def test_wrong_shape():
    r1 = np.zeros(shape=(1980, 720, 4))
    with pytest.raises(AssertionError, match='RGB'):
        mae(r1, r1)
        mse(r1, r1)

    r1 = r1[:,:,0:3]
    r2 = np.zeros(shape=(600, 600, 3))
    with pytest.raises(AssertionError, match='shape'):
        mae(r1, r2)
        mse(r1, r2)

def test_against_expected():
    r1 = np.zeros(shape=(2, 2, 3), dtype=np.int8)
    r2 = np.asarray([[[1, 1, 1],
                      [5, 2, 10]],

                     [[3, 1, 4],
                      [6, 8, 10]]], dtype=np.int8)
    expected_err = 13                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    
    expected_var = 65.5
    err, var, _ = mae(r1, r2, gray_scale=False)
    assert expected_err == err, f"Computed error: {err}, expected error: {expected_err}"
    assert expected_var == var, f"Computed error: {var}, expected error: {expected_var}"

    expected_err = 89.5                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    
    expected_var = 6321.25
    err, var, _ = mse(r1, r2, gray_scale=False)
    assert expected_err == err, f"Computed error: {err}, expected error: {expected_err}"
    assert expected_var == var, f"Computed error: {var}, expected error: {expected_var}"