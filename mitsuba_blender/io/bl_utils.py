
import bpy

def init_empty_scene(name='Scene'):
    ''' Create an empty Blender scene with a specific name.

    If a scene already exists with the same name, it will be
    cleared.

    Params
    ------
    name : str, optional
        Name of the newly created scene

    Returns
    -------
    The newly created Blender scene
    '''
    # Create a temporary scene to be able to delete others.
    # This is required as Blender needs at least one scene
    tmp_scene = bpy.data.scenes.new('mi-tmp')

    # Check if the scene already exists
    bl_scene = bpy.data.scenes.get(name)
    if bl_scene is not None:
        # Delete the scene if it exists
        bpy.data.scenes.remove(bl_scene)

    bl_scene = bpy.data.scenes.new(name)

    # Delete the temporary scene
    bpy.data.scenes.remove(tmp_scene)

    # Clear all orphaned data
    bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)

    return bl_scene
