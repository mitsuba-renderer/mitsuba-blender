if "bpy" in locals():
    import importlib
    if "bl_utils" in locals():
        importlib.reload(bl_utils)
    if "importer" in locals():
        importlib.reload(importer)

import bpy
from bpy.props import (
        StringProperty,
        BoolProperty,
    )
from bpy_extras.io_utils import (
        ImportHelper,
        orientation_helper,
        axis_conversion
    )

from . import bl_utils
from .export import MitsubaFileExport

@orientation_helper(axis_forward='-Z', axis_up='Y')
class ImportMistuba(bpy.types.Operator, ImportHelper):
    """Import a Mitsuba 2 scene"""
    bl_idname = "import_scene.mitsuba2"
    bl_label = "Mitsuba 2 Import"

    filename_ext = ".xml"
    filter_glob: StringProperty(default="*.xml", options={'HIDDEN'})

    override_scene: BoolProperty(
        name = 'Override Scene',
        description = 'Override the current scene with imported Mitsuba scene. '
                      'This will remove all current objects in the scene!',
        default = True,
    )

    def execute(self, context):
        # Set blender to object mode
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')

        axis_mat = axis_conversion(
            to_forward=self.axis_forward,
            to_up=self.axis_up,
        ).to_4x4()

        if self.override_scene:
            # Clear the scenes and create one for Mitsuba objects
            scene = bl_utils.init_empty_scene(context, name='Mitsuba2')
            collection = bl_utils.init_empty_collection(scene)
        else:
            # Create a collection for Mitsuba objects
            scene = context.scene
            collection = bl_utils.init_empty_collection(scene, name='Mitsuba2')

        from . import importer
        try:
            importer.load_mitsuba_scene(context, scene, collection, self.filepath, axis_mat)
        except (RuntimeError, NotImplementedError) as e:
            print(e)
            self.report({'ERROR'}, "Failed to load Mitsuba2 scene. See error log.")
            return {'CANCELLED'}

        self.report({'INFO'}, "Scene imported successfully.")

        return {'FINISHED'}


def menu_export_func(self, context):
    self.layout.operator(MitsubaFileExport.bl_idname, text="Mitsuba 2 (.xml)")

def menu_import_func(self, context):
    self.layout.operator(ImportMistuba.bl_idname, text="Mitsuba 2 (.xml)")


classes = (
    ImportMistuba,
    MitsubaFileExport
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.TOPBAR_MT_file_export.append(menu_export_func)
    bpy.types.TOPBAR_MT_file_import.append(menu_import_func)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

    bpy.types.TOPBAR_MT_file_export.remove(menu_export_func)
    bpy.types.TOPBAR_MT_file_import.remove(menu_import_func)
