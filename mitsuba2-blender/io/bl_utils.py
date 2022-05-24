
import bpy

def init_empty_scene(bl_context, name='Scene', clear_all_scenes=False):
    ''' Create an empty Blender scene with a specific name.
    
    If a scene already exists with the same name, it will be 
    cleared.

    Params
    ------
    bl_context : Blender context
    name : str, optional
        Name of the newly created scene
    clear_all_scenes : bool, optional
        Delete all other scenes from the context

    Returns
    -------
    The newly created Blender scene
    '''
    # Create a temporary scene to be able to delete others.
    # This is required as Blender needs at least one scene
    tmp_scene = bpy.data.scenes.new('mi-tmp')
    
    if clear_all_scenes:
        # Delete all scenes that are not the temporary one
        for scene in bpy.data.scenes:
            if scene.name != 'mi-tmp':
                bpy.data.scenes.remove(scene)
    
    # Check if the scene already exists
    bl_scene = bpy.data.scenes.get(name)
    if bl_scene is not None:
        # Delete the scene if it exists
        bpy.data.scenes.remove(bl_scene)

    bl_scene = bpy.data.scenes.new(name)

    # Delete the temporary scene
    bpy.data.scenes.remove(tmp_scene)

    # Clear all orphaned data
    if bpy.app.version < (2, 93, 0):
        bpy.ops.outliner.orphans_purge()
    else:
        bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
    
    return bl_scene

def init_empty_collection(bl_scene, name='Collection'):
    ''' Create an empty Blender collection with a specific name
    in the provided scene.

    If a collection already exists with the same name, it will be
    cleared.
    
    Params
    ------
    bl_scene : Blender scene to instantiate the collection into
    name : str, optional
        The name of the new collection

    Returns
    -------
    The newly created Blender collection
    '''
    # Check if the collection already exists
    bl_collection = bpy.data.collections.get(name)
    if bl_collection is not None:
        # Delete the collection if it exists
        for obj in bl_collection.objects:
            bpy.data.objects.remove(obj)
        bpy.data.collections.remove(bl_collection)
    else:
        # Create the new collection
        bl_collection = bpy.data.collections.new(name)
    # Link the collection to the scene
    bl_scene.collection.children.link(bl_collection)
    return bl_collection