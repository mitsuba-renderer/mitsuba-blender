from mathutils import Color

def rgb_to_rgba(color):
    return color + [1.0]

def rgba_to_rgb(color):
    return Color(color[0], color[1], color[2])
