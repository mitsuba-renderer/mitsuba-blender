"""The IES profile parser and its Cycles-compatible evaluation."""

import importlib
import math
from pathlib import Path

import numpy as np
import pytest

RES = Path(__file__).resolve().parent.parent / 'res' / 'ies'

# 4 pi / 177.83, Cycles' candela to watt factor
CANDELA_TO_WATT = 0.0706650768394


@pytest.fixture(scope='session')
def ies(mi_addon):
    return importlib.import_module(f'{mi_addon}.convert.export.ies')


def test_parse_symmetric_type_c(ies):
    profile = ies.parse_ies((RES / 'narrow_spot.ies').read_text())
    # A single horizontal plane is duplicated at 360 degrees
    assert np.allclose(np.degrees(profile.h_angles), [0.0, 360.0])
    assert profile.intensity.shape == (2, 10)
    assert profile.symmetric
    # Candela multiplier 1.5 and the candela to watt factor apply
    assert profile.intensity[0, 0] == pytest.approx(1000 * 1.5 * CANDELA_TO_WATT)
    assert profile.interpolate(math.pi, 0.0) == pytest.approx(
        1000 * 1.5 * CANDELA_TO_WATT)
    # Zero beyond the last vertical angle
    assert profile.interpolate(math.pi, math.radians(90)) == 0.0
    assert profile.interpolate(math.pi, math.radians(120)) == 0.0


def test_parse_quadrants(ies):
    profile = ies.parse_ies((RES / 'quadrants.ies').read_text())
    assert not profile.symmetric
    assert np.allclose(np.degrees(profile.h_angles), [0, 90, 180, 270, 360])
    # Table nodes are reproduced exactly
    for h, expected in ((0, 100), (90, 50), (180, 100), (270, 200)):
        value = profile.interpolate(math.radians(h) + 1e-9, 1e-9)
        assert value == pytest.approx(expected * CANDELA_TO_WATT, rel=1e-6)
    # The Cycles convention: v from the -Z axis, h = atan2(x, y) + pi, so
    # the +Y half-space maps to h = 180 degrees and +X to 270 degrees
    assert ies.light_direction_factor(profile, (0, 0, -1)) == \
        pytest.approx(100 * CANDELA_TO_WATT, rel=1e-6)
    v = math.radians(30)
    assert ies.light_direction_factor(profile, (0, math.sin(v), -math.cos(v))) \
        == pytest.approx(80 * CANDELA_TO_WATT, rel=1e-6)
    assert ies.light_direction_factor(profile, (math.sin(v), 0, -math.cos(v))) \
        == pytest.approx(160 * CANDELA_TO_WATT, rel=1e-6)
    assert ies.light_direction_factor(profile, (-math.sin(v), 0, -math.cos(v))) \
        == pytest.approx(40 * CANDELA_TO_WATT, rel=1e-6)


def test_parse_commas_and_tilt_include(ies):
    text = ('IESNA91\n[TEST] commas\nTILT=INCLUDE\n1 2\n0 90\n1 1\n'
            '1,100,2,3,1,1,2,0,0,0\n1,1,0\n0,45,90\n0\n10,5,0\n')
    profile = ies.parse_ies(text)
    assert profile.intensity.shape == (2, 3)
    assert profile.intensity[0, 0] == pytest.approx(20 * CANDELA_TO_WATT)


def test_type_a_and_b_are_mapped_to_type_c(ies):
    header = 'IESNA91\nTILT=NONE\n1 100 1 3 2 {type} 2 0 0 0\n1 1 0\n'
    # Type A: vertical -90..90 becomes 0..180, horizontal 0..90 is mirrored
    text = header.format(type=3) + '-90 0 90\n0 90\n1 2 3\n4 5 6\n'
    profile = ies.parse_ies(text)
    assert np.allclose(np.degrees(profile.v_angles), [0, 90, 180])
    assert np.allclose(np.degrees(profile.h_angles), [90, 180, 270])
    assert np.allclose(profile.intensity / CANDELA_TO_WATT,
                       [[4, 5, 6], [1, 2, 3], [4, 5, 6]])
    # Type B: the angle tables are transposed, the new horizontal range
    # -90..90 is shifted to 0..180 and the new vertical range 0..90 is
    # mirrored to 0..180
    text = header.format(type=2) + '-90 0 90\n0 90\n1 2 3\n4 5 6\n'
    profile = ies.parse_ies(text)
    assert np.allclose(np.degrees(profile.v_angles), [0, 90, 180])
    assert np.allclose(np.degrees(profile.h_angles), [0, 90, 180])
    assert np.allclose(profile.intensity / CANDELA_TO_WATT,
                       [[4, 1, 4], [5, 2, 5], [6, 3, 6]])


def test_half_and_quarter_profiles_are_mirrored(ies):
    header = 'IESNA91\nTILT=NONE\n1 100 1 2 {h} 1 2 0 0 0\n1 1 0\n0 90\n'
    profile = ies.parse_ies(header.format(h=3) + '0 45 90\n1 2\n3 4\n5 6\n')
    assert np.allclose(np.degrees(profile.h_angles),
                       [0, 45, 90, 135, 180, 225, 270, 315, 360])
    assert np.allclose(profile.intensity[:, 0] / CANDELA_TO_WATT,
                       [1, 3, 5, 3, 1, 3, 5, 3, 1])
    # A missing 360 degree entry is filled in from the first one
    profile = ies.parse_ies(header.format(h=4)
                            + '0 90 180 270\n1 2\n3 4\n5 6\n7 8\n')
    assert np.allclose(np.degrees(profile.h_angles), [0, 90, 180, 270, 360])
    assert np.allclose(profile.intensity[:, 0] / CANDELA_TO_WATT,
                       [1, 3, 5, 7, 1])


@pytest.mark.parametrize('text', ['', 'no tilt line', 'IESNA\nTILT=NONE\n',
                                  'IESNA\nTILT=NONE\n1 1 1 2 1 5 2 0 0 0\n'])
def test_rejected_files(ies, text):
    with pytest.raises(ValueError):
        ies.parse_ies(text)


def test_resample_matches_interpolation(ies):
    profile = ies.parse_ies((RES / 'quadrants.ies').read_text())
    table, bounds = profile.resample()
    assert table.shape == (181, 73)
    assert np.degrees(bounds) == pytest.approx([0, 120, 0, 360])
    for i in (0, 17, 45, 100):
        for j in (0, 10, 36, 72):
            v, h = math.radians(i), math.radians(5 * j)
            expected = profile.interpolate(min(h, 2 * math.pi - 1e-6),
                                           min(v, bounds[1] - 1e-6))
            assert table[i, j] == pytest.approx(expected, rel=1e-6)
    # Rows beyond the profile's range are zero
    assert not table[121:].any()

    profile = ies.parse_ies((RES / 'narrow_spot.ies').read_text())
    table, bounds = profile.resample()
    assert table.shape == (181, 1)
    assert np.degrees(bounds) == pytest.approx([0, 90, 0, 360])


def test_ies_text_roundtrip(ies):
    profile = ies.parse_ies((RES / 'quadrants.ies').read_text())
    table, _ = profile.resample()
    again = ies.parse_ies(ies.ies_text(table))
    assert again.intensity.shape == (73, 181)
    assert np.allclose(again.intensity.T, table, rtol=1e-4, atol=1e-6)
    table, _ = ies.parse_ies((RES / 'narrow_spot.ies').read_text()).resample()
    again = ies.parse_ies(ies.ies_text(table))
    assert again.intensity.shape == (2, 181)
    assert np.allclose(again.intensity[0], table[:, 0], rtol=1e-4, atol=1e-6)
