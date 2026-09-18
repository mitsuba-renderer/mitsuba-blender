'''IES photometric profiles, parsed and evaluated the way Cycles does.

The parser follows ``cycles/src/util/ies.cpp``: the candela values are
multiplied by the file's candela multiplier and ballast factors and
converted to the watt-like unit of Cycles light strengths, and type A and
B files are mapped onto the type C coordinate system. ``interpolate``
reproduces the lookup of ``cycles/src/kernel/util/ies.h``, and
``resample`` tabulates it on regular angle grids for the cycles_lights
shape plugin.
'''

import math

import numpy as np

# 4 pi / 177.83: candela to the watts that Cycles assigns to a light of
# the D65 illuminant spectrum
CANDELA_TO_WATT = 0.0706650768394

TYPE_C, TYPE_B, TYPE_A = 1, 2, 3


def _angle_close(a, b):
    return abs(a - b) < 1e-4


class IESProfile:
    '''A luminous intensity distribution over the sphere. ``v_angles``
    (polar, from the light's -Z axis) and ``h_angles`` (azimuth, from the
    +Y axis towards +X, both in radians) index the ``intensity`` array of
    shape (h_num, v_num).'''

    def __init__(self, v_angles, h_angles, intensity):
        self.v_angles = np.asarray(v_angles, dtype=np.float64)
        self.h_angles = np.asarray(h_angles, dtype=np.float64)
        self.intensity = np.asarray(intensity, dtype=np.float64)

    @property
    def symmetric(self):
        '''Whether the intensity does not depend on the horizontal angle'''
        return bool(np.all(self.intensity == self.intensity[0]))

    def interpolate(self, h_angle, v_angle):
        '''Cycles' cubic interpolation of the table (kernel_ies_interp).
        Zero outside the tabulated angles.'''
        v, h, values = self.v_angles, self.h_angles, self.intensity
        v_num, h_num = len(v), len(h)
        if v_angle < v[0] or v_angle >= v[-1]:
            return 0.0
        if h_angle < h[0] or h_angle >= h[-1]:
            return 0.0
        wrap_h = h[0] < 1e-7 and h[-1] > 2.0 * math.pi - 1e-7
        wrap_vlow = v[0] < 1e-7
        wrap_vhigh = v[-1] > math.pi - 1e-7

        h_i = int(np.searchsorted(h, h_angle, side='right')) - 1
        v_i = int(np.searchsorted(v, v_angle, side='right')) - 1
        h_i = min(h_i, h_num - 2)
        v_i = min(v_i, v_num - 2)
        h_frac = (h_angle - h[h_i]) / (h[h_i + 1] - h[h_i])
        v_frac = (v_angle - v[v_i]) / (v[v_i + 1] - v[v_i])

        def vertical(col):
            row = values[col]
            b, c = row[v_i], row[v_i + 1]
            a = b
            if v_i > 0:
                a = row[v_i - 1]
            elif wrap_vlow:
                a = row[1]
            d = c
            if v_i + 2 < v_num:
                d = row[v_i + 2]
            elif wrap_vhigh:
                d = row[v_num - 2]
            return _cubic(a, b, c, d, v_frac)

        b = vertical(h_i)
        c = vertical(h_i + 1)
        a = b
        if h_i > 0:
            a = vertical(h_i - 1)
        elif wrap_h:
            a = vertical(h_num - 2)
        d = b
        if h_i + 2 < h_num:
            d = vertical(h_i + 2)
        elif wrap_h:
            d = vertical(1)
        return max(_cubic(a, b, c, d, h_frac), 0.0)

    def resample(self, max_step=5.0):
        '''Tabulate the profile on regular grids: polar angles from 0 to
        180 degrees and azimuths from 0 to 360 degrees, with steps no
        larger than ``max_step`` degrees (vertically at most one degree)
        and no larger than the file's own. A symmetric profile gets a
        single column. Returns the (v_num, h_num) table and the angular
        range (v_low, v_high, h_low, h_high) in radians outside which the
        profile is zero.'''
        def count(angles, span, max_step):
            steps = np.diff(angles)
            steps = np.degrees(steps[steps > 1e-7])
            step = min(steps.min(), max_step) if len(steps) else max_step
            return round(span / step) + 1

        v_num = count(self.v_angles, 180.0, min(max_step, 1.0))
        h_num = 1 if self.symmetric else count(self.h_angles, 360.0, max_step)
        # Cycles returns zero at the upper bounds of the range, but the shape
        # plugin applies the range itself, so the grid nodes on the bounds
        # hold the limit values
        def clamp(angle, bound):
            return bound - 1e-6 if abs(angle - bound) < 1e-6 else angle

        table = np.zeros((v_num, h_num))
        for i in range(v_num):
            v_angle = clamp(math.pi * i / (v_num - 1), self.v_angles[-1])
            for j in range(h_num):
                h_angle = 2.0 * math.pi * j / max(h_num - 1, 1)
                h_angle = clamp(h_angle, self.h_angles[-1])
                table[i, j] = self.interpolate(h_angle, v_angle)
        v_range = (float(self.v_angles[0]), float(self.v_angles[-1]))
        h_range = (float(self.h_angles[0]), float(self.h_angles[-1]))
        if h_num == 1:
            h_range = (0.0, 2.0 * math.pi)
        return table, v_range + h_range


def _cubic(a, b, c, d, x):
    return 0.5 * (((d + 3.0 * (b - c) - a) * x
                   + (2.0 * a - 5.0 * b + 4.0 * c - d)) * x + (c - a)) * x + b


class _Tokens:
    def __init__(self, text):
        self.tokens = text.replace(',', ' ').split()
        self.pos = 0

    def number(self):
        if self.pos >= len(self.tokens):
            raise ValueError('unexpected end of file')
        token = self.tokens[self.pos]
        self.pos += 1
        try:
            return float(token)
        except ValueError:
            raise ValueError(f'expected a number, found "{token}"') from None

    def integer(self):
        return int(self.number())


def parse_ies(text):
    '''Parse the contents of an IES file into an IESProfile. Raises
    ValueError for files that Cycles would reject as well.'''
    if not isinstance(text, str):
        text = text.decode('utf-8', errors='replace')
    tilt = text.find('\nTILT=')
    if tilt < 0:
        raise ValueError('no TILT line')
    rest = text[tilt + 1:]
    if rest.startswith('TILT=INCLUDE'):
        tokens = _Tokens(rest[len('TILT=INCLUDE'):])
        tokens.number()  # lamp to luminaire geometry
        num_tilt = tokens.integer()
        for _ in range(2 * num_tilt):
            tokens.number()
    else:
        newline = rest.find('\n')
        if newline < 0:
            raise ValueError('unexpected end of file')
        tokens = _Tokens(rest[newline + 1:])

    tokens.integer()  # number of lamps
    tokens.number()  # lumens per lamp
    factor = tokens.number()  # candela multiplier
    v_num = tokens.integer()
    h_num = tokens.integer()
    ies_type = tokens.integer()
    if ies_type not in (TYPE_A, TYPE_B, TYPE_C):
        raise ValueError(f'unsupported photometric type {ies_type}')
    tokens.integer()  # unit of the geometry data
    for _ in range(3):
        tokens.number()  # width, length, height
    factor *= tokens.number()  # ballast factor
    factor *= tokens.number()  # ballast-lamp photometric factor
    tokens.number()  # input watts
    factor *= CANDELA_TO_WATT

    v_angles = [tokens.number() for _ in range(v_num)]
    h_angles = [tokens.number() for _ in range(h_num)]
    intensity = [[factor * tokens.number() for _ in range(v_num)]
                 for _ in range(h_num)]
    if not v_angles or not h_angles:
        raise ValueError('empty angle table')

    if ies_type == TYPE_A:
        v_angles, h_angles, intensity = _process_type_a(v_angles, h_angles,
                                                        intensity)
    elif ies_type == TYPE_B:
        v_angles, h_angles, intensity = _process_type_b(v_angles, h_angles,
                                                        intensity)
    else:
        v_angles, h_angles, intensity = _process_type_c(v_angles, h_angles,
                                                        intensity)
    return IESProfile(np.radians(v_angles), np.radians(h_angles), intensity)


def _process_type_b(v_angles, h_angles, intensity):
    '''Type B has a horizontal polar axis. Cycles transposes the angles
    and treats the result like type A / C, leaving the light's rotation
    to the user.'''
    intensity = [list(col) for col in zip(*intensity)]
    h_angles, v_angles = v_angles, h_angles

    if _angle_close(h_angles[0], 0.0):
        # 0 to 90 degrees: mirror to -90..90, then shift to 0..180
        new_h = [90.0 - a for a in reversed(h_angles[1:])] \
            + [90.0 + a for a in h_angles]
        intensity = list(reversed(intensity[1:])) + intensity
        h_angles = new_h
    else:
        h_angles = [a + 90.0 for a in h_angles]

    if _angle_close(v_angles[0], 0.0):
        v_angles = [90.0 - a for a in reversed(v_angles[1:])] \
            + [90.0 + a for a in v_angles]
        intensity = [list(reversed(row[1:])) + list(row) for row in intensity]
    else:
        v_angles = [a + 90.0 for a in v_angles]
    return v_angles, h_angles, intensity


def _process_type_a(v_angles, h_angles, intensity):
    v_angles = [a + 90.0 for a in v_angles]
    # Type A spans -90 to 90 degrees, mapped to 270 down to 90 in type C
    new_h = [180.0 - a for a in reversed(h_angles)]
    new_intensity = list(reversed(intensity))
    if _angle_close(h_angles[0], 0.0):
        # Mirror the missing negative range, which lands on 180..270
        new_h += [180.0 + a for a in h_angles[1:]]
        new_intensity += intensity[1:]
    return v_angles, new_h, new_intensity


def _process_type_c(v_angles, h_angles, intensity):
    h_angles, intensity = list(h_angles), list(intensity)
    if _angle_close(h_angles[0], 90.0):
        h_angles = [a - 90.0 for a in h_angles]
    if len(h_angles) == 1:
        h_angles = [0.0, 360.0]
        intensity.append(intensity[0])
    if _angle_close(h_angles[-1], 90.0):
        # One quadrant: mirror it to two, the next step mirrors to four
        n = len(h_angles)
        for i in range(n - 2, -1, -1):
            h_angles.append(180.0 - h_angles[i])
            intensity.append(intensity[i])
    if _angle_close(h_angles[-1], 180.0):
        n = len(h_angles)
        for i in range(n - 2, -1, -1):
            h_angles.append(360.0 - h_angles[i])
            intensity.append(intensity[i])
    if _angle_close(h_angles[0], 0.0) and not _angle_close(h_angles[-1], 360.0):
        # Some files leave out the 360 degree entry that equals the first
        last_step = h_angles[-1] - h_angles[-2]
        first_step = h_angles[1] - h_angles[0]
        gap = 360.0 - h_angles[-1]
        if _angle_close(last_step, gap) or _angle_close(first_step, gap):
            h_angles.append(360.0)
            intensity.append(intensity[0])
    return v_angles, h_angles, intensity


def format_table(table):
    '''Text form of a resampled table for the cycles_lights shape: one
    line per polar angle, values in Cycles' watt-like unit.'''
    return '\n'.join(' '.join(f'{x:.5g}' for x in row) for row in table)


def ies_text(table):
    '''A type C IES file holding a resampled table of the cycles_lights
    shape (rows over 0..180 degrees, columns over 0..360 degrees), for the
    importer. The values return to candela.'''
    table = np.asarray(table, dtype=np.float64)
    rows, columns = table.shape
    v_angles = [180.0 * i / (rows - 1) for i in range(rows)]
    if columns == 1:
        h_angles = [0.0]
    else:
        h_angles = [360.0 * j / (columns - 1) for j in range(columns)]
    lines = ['IESNA:LM-63-2002', '[MANUFAC] mitsuba-blender', 'TILT=NONE',
             f'1 -1 1 {rows} {columns} 1 2 0 0 0', '1 1 0',
             ' '.join(f'{a:g}' for a in v_angles),
             ' '.join(f'{a:g}' for a in h_angles)]
    for j in range(columns):
        lines.append(' '.join(f'{x / CANDELA_TO_WATT:.5g}'
                              for x in table[:, j]))
    return '\n'.join(lines) + '\n'


def light_direction_factor(profile, local_dir):
    '''Value of the profile for an emission direction in the light's local
    frame, as Cycles' IES node computes it from its Vector input.'''
    x, y, z = local_dir
    norm = math.sqrt(x * x + y * y + z * z)
    x, y, z = x / norm, y / norm, z / norm
    v_angle = math.acos(max(min(-z, 1.0), -1.0))
    h_angle = math.atan2(x, y) + math.pi
    return profile.interpolate(h_angle, v_angle)
