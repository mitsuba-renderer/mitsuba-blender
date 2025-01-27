
import bpy
from bpy.props import *
from bpy_extras.io_utils import ImportHelper, orientation_helper, axis_conversion

from .. import importer
from .. import logging

@orientation_helper(axis_forward='-Z', axis_up='Y')
class ImportMitsubaBase(bpy.types.Operator, ImportHelper):
    '''
    Import a Mitsuba scene
    '''
    mode: EnumProperty(
        name = 'Import mode',
        description = 'Import mode, defining whether the loaded scene should be appended to the current scene or override the existing scene, or create a new one.',
        items=[
            ('append', 'append', 'Append the objects of the imported scene to the current scene'),
            ('override', 'override', 'Override the current scene with the imported scene'),
            ('new', 'new', 'Create a new scene')
        ],
        default = "override",
    )

    def call_loader(self, context, scene, collection, axis_mat):
        pass

    def execute(self, context):
        # Set blender to object mode
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')

        axis_mat = axis_conversion(
            to_forward=self.axis_forward,
            to_up=self.axis_up,
        ).to_4x4()

        if self.mode == 'append':
            scene = bpy.context.scene
        elif self.mode == 'override':
            # Clear the current scene
            scene = init_empty_scene(context, name=bpy.context.scene.name)
        else:
            # Create a new scene for Mitsuba objects
            scene = init_empty_scene(context, name='Mitsuba asset')
        collection = scene.collection

        try:
            self.call_loader(context, scene, collection, axis_mat)
        except (RuntimeError, NotImplementedError) as e:
            self.report({'ERROR'}, "Failed to load Mitsuba scene. See error log.")
            logging.error(e)
            return {'CANCELLED'}

        bpy.context.window.scene = scene

        self.report({'INFO'}, "Scene imported successfully.")
        logging.info("Scene imported successfully!")

        return {'FINISHED'}


@orientation_helper(axis_forward='-Z', axis_up='Y')
class ImportMitsubaXML(ImportMitsubaBase):
    '''
    Import a Mitsuba XML scene
    '''
    bl_idname = "import_scene_xml.mitsuba_engine"
    bl_label = "Mitsuba Import XML"

    filename_ext = ".xml"
    filter_glob: StringProperty(default="*.xml", options={'HIDDEN'})

    def call_loader(self, context, scene, collection, axis_mat):
        importer.load_mitsuba_scene(context, scene, collection, axis_mat, scene_filepath=self.filepath)

# ------------------------------------------------------------------------------

def init_empty_scene(bl_context, name='Scene', clear_all_scenes=False):
    '''
    Create an empty Blender scene with a specific name.

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
        # Clear all orphaned data
        if bpy.app.version < (2, 93, 0):
            # NOTE: Calling `orphans_purge` on Blender 2.83
            #       results in a segfault.
            for data_type in (
                bpy.data.objects,
                bpy.data.meshes,
                bpy.data.cameras,
                bpy.data.images,
                bpy.data.lights,
                bpy.data.materials,
                bpy.data.meshes,
                bpy.data.textures,
                bpy.data.worlds
            ):
                for data in data_type:
                    if data and data.users == 0:
                        data_type.remove(data)
        else:
            bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)

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
    '''
    Create an empty Blender collection with a specific name
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