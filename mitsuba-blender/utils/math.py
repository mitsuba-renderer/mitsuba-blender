def decompose_transform_2d(transform):
    from drjit import transform_decompose, quat_to_euler
    scale, quat, translation = transform_decompose(transform.matrix)
    rotation = quat_to_euler(quat)
    translation = [translation[0], translation[1]]
    scale = [scale[0,0], scale[1,1]]
    rotation = rotation[2]
    return translation, rotation, scale

def compose_transform_2d(translation, rotation, scale):
    from drjit import transform_compose, euler_to_quat
    s = [[scale[0], 0.0, 0.0], [0.0, scale[1], 0.0], [0.0, 0.0, 1.0]]
    # FIXME: Dr.JIT does not understand this.
    euler = [0.0, 0.0, rotation]
    q = euler_to_quat(euler)
    t = [translation[0], translation[1], 0.0]
    transform = transform_compose(s, q, t)
    return transform
