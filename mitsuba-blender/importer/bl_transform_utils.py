from mathutils import Matrix

def mi_transform_to_bl_transform(matrix):
    return Matrix(matrix.matrix.numpy()) if matrix is not None else Matrix()
