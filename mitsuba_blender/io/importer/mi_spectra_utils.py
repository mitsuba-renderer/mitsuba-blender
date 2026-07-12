
def get_color_strength_from_radiance(radiance):
    # FIXME: Find a proper way of converting radiance to color/energy
    strength = max(radiance)
    if strength < 1.0:
        return radiance, 1.0
    return [c / strength for c in radiance], strength
