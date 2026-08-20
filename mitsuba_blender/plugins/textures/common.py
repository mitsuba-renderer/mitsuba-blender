import mitsuba as mi
import drjit as dr


class ConstantVector(mi.Texture):
    ''' A fixed three-component value. Unlike Mitsuba's rgb texture this
    carries no reflectance semantics, so components outside [0, 1] are
    allowed.'''

    def __init__(self, value):
        super().__init__(mi.Properties())
        if isinstance(value, (int, float)):
            self.value = mi.Color3f(value)
        else:
            self.value = mi.Color3f(value[0], value[1], value[2])


    def eval(self, si, active=True):
        return mi.UnpolarizedSpectrum(self.value)

    def eval_1(self, si, active=True):
        return (self.value.x + self.value.y + self.value.z) * (1.0 / 3.0)

    def eval_3(self, si, active=True):
        return self.value

    def mean(self):
        return 0.5


def register(mi, dr):
    mi.register_texture('constant_vector', ConstantVector)


def get_texture(props: mi.Properties,
                name: str,
                value=None) -> mi.Texture:
    '''
    Helper function to check when a node is active in `props`
    Authors: Sebastien Speierer, Baptiste Nicolet
    '''
    if name not in props:
        if value is None:
            raise Exception(f'Property {name} has not been specified!')
        if isinstance(value, (float, int)):
            return mi.load_dict({ 'type': 'uniform', 'value': value }, parallel=False)
        return mi.load_dict({'type': 'rgb', 'value': value }, parallel=False)
    texture = props.get(name)
    if isinstance(texture, (float, int)):
        return mi.load_dict({ 'type': 'uniform', 'value': texture }, parallel=False)
    if not isinstance(texture, mi.Texture):
        return mi.load_dict({ 'type': 'rgb', 'value': texture }, parallel=False)
    return texture


def get_vector_texture(props, name, default=0.0):
    """As get_texture, but for vector-valued properties. Constants are kept
    as raw values rather than wrapped in an rgb texture, whose reflectance
    range would reject components outside [0, 1]."""
    if name not in props:
        return ConstantVector(default)
    value = props.get(name)
    if isinstance(value, mi.Texture):
        return value
    return ConstantVector(value)

# Those functions are taken directly from Blender implementation
# see: https://github.com/blender/blender/blob/main/source/blender/blenlib/intern/math_color.cc

def rgb2hsv(rgb):
    r, g, b = rgb.x, rgb.y, rgb.z

    swap_gb = g < b
    g2 = dr.select(swap_gb, b, g)
    b2 = dr.select(swap_gb, g, b)
    k = dr.select(swap_gb, -1.0, 0.0)

    swap_rg = r < g2
    r3 = dr.select(swap_rg, g2, r)
    g3 = dr.select(swap_rg, r, g2)
    k = dr.select(swap_rg, -2.0 / 6.0 - k, k)
    min_gb = dr.select(swap_rg, dr.minimum(g3, b2), b2)

    chroma = r3 - min_gb
    return mi.Color3f(dr.abs(k + (g3 - b2) / (6.0 * chroma + 1e-20)),
                      chroma / (r3 + 1e-20),
                      r3)

def _mod(a, b):
    return a - b * dr.floor(a / b)

def hsv2rgb(hsv):
    h, s, v = hsv.x, hsv.y, hsv.z
    nr = dr.clip(dr.abs(h * 6.0 - 3.0) - 1.0, 0.0, 1.0)
    ng = dr.clip(2.0 - dr.abs(h * 6.0 - 2.0), 0.0, 1.0)
    nb = dr.clip(2.0 - dr.abs(h * 6.0 - 4.0), 0.0, 1.0)
    return mi.Color3f(((nr - 1.0) * s + 1.0) * v,
                      ((ng - 1.0) * s + 1.0) * v,
                      ((nb - 1.0) * s + 1.0) * v)

def hsl2rgb(hsl):
    h, s, l = hsl.x, hsl.y, hsl.z
    nr = dr.clip(dr.abs(h * 6.0 - 3.0) - 1.0, 0.0, 1.0)
    ng = dr.clip(2.0 - dr.abs(h * 6.0 - 2.0), 0.0, 1.0)
    nb = dr.clip(2.0 - dr.abs(h * 6.0 - 4.0), 0.0, 1.0)
    chroma = (1.0 - dr.abs(2.0 * l - 1.0)) * s
    return mi.Color3f((nr - 0.5) * chroma + l,
                      (ng - 0.5) * chroma + l,
                      (nb - 0.5) * chroma + l)



def rgb2hsl(rgb):
    r, g, b = rgb.x, rgb.y, rgb.z
    cmax = dr.maximum(r, dr.maximum(g, b))
    cmin = dr.minimum(r, dr.minimum(g, b))
    l = dr.minimum(1.0, (cmax + cmin) * 0.5)

    d = cmax - cmin
    achromatic = d == 0.0
    d_safe = dr.select(achromatic, 1.0, d)

    s = dr.select(l > 0.5,
                  d_safe / dr.maximum(2.0 - cmax - cmin, 1e-20),
                  d_safe / dr.maximum(cmax + cmin, 1e-20))

    h = dr.select(cmax == r,
                  (g - b) / d_safe + dr.select(g < b, 6.0, 0.0),
                  dr.select(cmax == g,
                            (b - r) / d_safe + 2.0,
                            (r - g) / d_safe + 4.0))
    h = h / 6.0

    h = dr.select(achromatic, 0.0, h)
    s = dr.select(achromatic, 0.0, s)
    return mi.Color3f(h, s, l)




