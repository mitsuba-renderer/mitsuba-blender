if "bpy" in locals():
    import importlib
    if "bl_utils" in locals():
        importlib.reload(bl_utils)
    if "importer" in locals():
        importlib.reload(importer)
    if "importer_yml" in locals():
        importlib.reload(importer_yml)
    if "exporter" in locals():
        importlib.reload(exporter)
    if "hdri_converter" in locals():
        importlib.reload(hdri_converter)

import bpy
from bpy.props import (
        StringProperty,
        BoolProperty,
        IntProperty,
        EnumProperty,
    )
from bpy_extras.io_utils import (
        ImportHelper,
        ExportHelper,
        orientation_helper,
        axis_conversion
    )

from . import bl_utils
from . import importer
from . import importer_yml
from . import exporter
from . import hdri_converter


@orientation_helper(axis_forward='-Z', axis_up='Y')
class ImportMitsuba(bpy.types.Operator, ImportHelper):
    """Import a Mitsuba scene"""
    bl_idname = "import_scene.mitsuba"
    bl_label = "Mitsuba Import"

    filename_ext = ".xml"
    filter_glob: StringProperty(default="*.xml", options={'HIDDEN'})

    override_scene: BoolProperty(
        name = 'Override Current Scene',
        description = 'Override the current scene with the imported Mitsuba scene. '
                      'Otherwise, creates a new scene for Mitsuba objects.',
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
            # Clear the current scene
            scene = bl_utils.init_empty_scene(context, name=bpy.context.scene.name)
        else:
            # Create a new scene for Mitsuba objects
            scene = bl_utils.init_empty_scene(context, name='Mitsuba')
        collection = scene.collection

        try:
            importer.load_mitsuba_scene(context, scene, collection, self.filepath, axis_mat)
        except (RuntimeError, NotImplementedError) as e:
            print(e)
            self.report({'ERROR'}, "Failed to load Mitsuba scene. See error log.")
            return {'CANCELLED'}

        bpy.context.window.scene = scene

        self.report({'INFO'}, "Scene imported successfully.")

        return {'FINISHED'}


@orientation_helper(axis_forward='-Z', axis_up='Y')
class ImportYMLConfig(bpy.types.Operator, ImportHelper):
    """Import a custom yml-description scene"""
    bl_idname = "import_scene.custom_yml"
    bl_label = "Custom YML Config Import"

    filename_ext = ".yml"
    filter_glob: StringProperty(default="*.yml", options={'HIDDEN'})

    override_scene: BoolProperty(
        name = 'Override Current Scene',
        description = 'Override the current scene with the imported Mitsuba scene. '
                      'Otherwise, creates a new scene for Mitsuba objects.',
        default = True,
    )

    def execute(self, context):
        # Set blender to object mode
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')

        if self.override_scene:
            # Clear the current scene
            scene = bl_utils.init_empty_scene(context, name=bpy.context.scene.name)
        else:
            # Create a new scene for Mitsuba objects
            scene = bl_utils.init_empty_scene(context, name='Mitsuba')

        try:
            importer_yml.build_new_scene(scene, self.filepath)
        except (RuntimeError, NotImplementedError) as e:
            print(e)
            self.report({'ERROR'}, "Failed to load scene from config. See error log.")
            return {'CANCELLED'}

        bpy.context.window.scene = scene

        self.report({'INFO'}, "Scene imported successfully.")

        return {'FINISHED'}


@orientation_helper(axis_forward='-Z', axis_up='Y')
class ExportMitsuba(bpy.types.Operator, ExportHelper):
    """Export as a Mitsuba scene"""
    bl_idname = "export_scene.mitsuba"
    bl_label = "Mitsuba Export"

    filename_ext = ".xml"
    filter_glob: StringProperty(default="*.xml", options={'HIDDEN'})

    use_selection: BoolProperty(
	        name = "Selection Only",
	        description="Export selected objects only",
	        default = False,
	    )

    split_files: BoolProperty(
            name = "Split File",
            description = "Split scene XML file in smaller fragments",
            default = False
    )

    export_ids: BoolProperty(
            name = "Export IDs",
            description = "Add an 'id' field for each object (shape, emitter, camera...)",
            default = False
    )

    ignore_background: BoolProperty(
            name = "Ignore Default Background",
            description = "Ignore blender's default constant gray background when exporting to Mitsuba.",
            default = True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reset()

    def reset(self):
        self.converter = exporter.SceneConverter()

    def execute(self, context):
        # Conversion matrix to shift the "Up" Vector. This can be useful when exporting single objects to an existing mitsuba scene.
        axis_mat = axis_conversion(
	            to_forward=self.axis_forward,
	            to_up=self.axis_up,
	        ).to_4x4()

        self.converter.export_ctx.axis_mat = axis_mat
        # Add IDs to all base plugins (shape, emitter, sensor...)
        self.converter.export_ctx.export_ids = self.export_ids

        self.converter.use_selection = self.use_selection

        # Set path to scene .xml file
        self.converter.set_path(self.filepath, split_files=self.split_files)

        window_manager = context.window_manager

        deps_graph = context.evaluated_depsgraph_get()

        total_progress = len(deps_graph.object_instances)
        window_manager.progress_begin(0, total_progress)

        self.converter.scene_to_dict(deps_graph, window_manager)
        # Write data to scene .xml file
        self.converter.dict_to_xml()

        window_manager.progress_end()

        self.report({'INFO'}, "Scene exported successfully!")

        # Reset the exporter
        self.reset()

        return {'FINISHED'}


@orientation_helper(axis_forward='-Z', axis_up='Y')
class ExportMitsubaExtended(bpy.types.Operator, ExportHelper):
    """Export the Mitsuba scene with auxiliary data"""
    bl_idname = "export_scene.mitsuba_optimization"
    bl_label = "Mitsuba Export For Optimization"

    filename_ext = ".xml"
    filter_glob: StringProperty(default="*.xml", options={'HIDDEN'})

    use_selection: BoolProperty(
	        name = "Selection Only",
	        description="Export selected objects only",
	        default = False,
	    )

    split_files: BoolProperty(
            name = "Split File",
            description = "Split scene XML file in smaller fragments",
            default = False
    )

    export_ids: BoolProperty(
            name = "Export IDs",
            description = "Add an 'id' field for each object (shape, emitter, camera...)",
            default = True
    )

    ignore_background: BoolProperty(
            name = "Ignore Default Background",
            description = "Ignore blender's default constant gray background when exporting to Mitsuba.",
            default = True
    )

    # HDRI Baking Settings
    hdri_resolution: EnumProperty(
        name="Resolution",
        description="HDRI resolution (must be 2:1 aspect ratio)",
        items=[
            ('2048', "2K (2048x1024)", "2K resolution"),
            ('4096', "4K (4096x2048)", "4K resolution (Standard)"),
            ('8192', "8K (8192x4096)", "8K resolution (High Quality)"),
            ('16384', "16K (16384x8192)", "16K resolution (Ultra Quality)"),
        ],
        default='4096'
    )

    hdri_output_format: EnumProperty(
        name="Format",
        description="Output file format for HDRI",
        items=[
            ('HDR', "Radiance HDR (.hdr)", "Radiance HDR format"),
            ('OPEN_EXR', "OpenEXR (.exr)", "OpenEXR format"),
        ],
        default='OPEN_EXR'
    )

    hdri_samples: IntProperty(
        name="Samples",
        description="Number of render samples",
        default=256,
        min=1,
        max=8192
    )

    def draw(self, context):
        layout = self.layout
        
        layout.prop(self, "use_selection")
        layout.prop(self, "split_files")
        layout.prop(self, "export_ids")
        layout.prop(self, "ignore_background")
        
        layout.prop(self, "axis_forward")
        layout.prop(self, "axis_up")
        
        scene = context.scene
        realsky_enabled = hasattr(scene, 'sky_settings') and scene.sky_settings.enabled
        
        if realsky_enabled:
            box = layout.box()
            box.label(text="HDRI Baking Settings:")
            box.prop(self, "hdri_resolution")
            box.prop(self, "hdri_output_format")
            box.prop(self, "hdri_samples")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reset()

    def reset(self):
        self.converter = exporter.SceneConverter(include_auxiliary_output=True)

    def execute(self, context):
        import os
        scene = context.scene
        
        # Check if environment is already an envmap
        is_envmap = False
        if scene.world and scene.world.use_nodes and scene.world.node_tree:
            output_node_id = 'World Output'
            if output_node_id in scene.world.node_tree.nodes:
                output_node = scene.world.node_tree.nodes[output_node_id]
                if output_node.inputs["Surface"].is_linked:
                    surface_node = output_node.inputs["Surface"].links[0].from_node
                    if surface_node.type in ['BACKGROUND', 'EMISSION']:
                        socket = surface_node.inputs["Color"]
                        if socket.is_linked:
                            color_node = socket.links[0].from_node
                            if color_node.type == 'TEX_ENVIRONMENT':
                                is_envmap = True

        realsky_enabled = hasattr(scene, 'sky_settings') and scene.sky_settings.enabled
        hidden_objects = []
        original_camera = scene.camera
        
        # bake the sky texture into an envmap if RealSky is enabled
        #TODO: add option to bake for any non-envmap/non-rgb background, not just RealSky (e.g. procedural sky texture nodes)
        #TODO: add option to skip HDRI baking and do not export background
        if not is_envmap and realsky_enabled:
            # Hide all non-RealSky objects for baking. Unhide them and hide the RealSky objects again after baking.
            realsky_names = ["cirrus", "cirrocumulus", "altostratus", "altostratus_mist", "altostratus_billboard", "cumulus", "cumulus_mist", "cumulus_billboard"]
            for obj in scene.objects:
                if obj.name not in realsky_names and not obj.hide_render:
                    obj.hide_render = True
                    hidden_objects.append(obj)
            
            hdri_filepath = os.path.join(os.path.dirname(self.filepath), "baked_envmap.exr")

            bpy.ops.render.convert_to_hdri(
                filepath=hdri_filepath, 
                output_format=self.hdri_output_format,
                resolution=self.hdri_resolution,
                samples=self.hdri_samples,
                clip_end=800000 if realsky_enabled else 1000
            )
            
            for obj in hidden_objects:
                obj.hide_render = False
                
            for obj in scene.objects:
                if obj.name in realsky_names or obj.name == "HDRI_Camera":
                    obj.hide_render = True
                
            scene.camera = original_camera
            
            if not scene.world.use_nodes:
                scene.world.use_nodes = True
            tree = scene.world.node_tree
            tree.nodes.clear()
            
            bg_node = tree.nodes.new(type='ShaderNodeBackground')
            env_node = tree.nodes.new(type='ShaderNodeTexEnvironment')
            out_node = tree.nodes.new(type='ShaderNodeOutputWorld')
            
            env_node.image = bpy.data.images.load(hdri_filepath)
            
            tree.links.new(env_node.outputs['Color'], bg_node.inputs['Color'])
            tree.links.new(bg_node.outputs['Background'], out_node.inputs['Surface'])
            
            scene.view_settings.exposure = -6

        # Conversion matrix to shift the "Up" Vector. This can be useful when exporting single objects to an existing mitsuba scene.
        axis_mat = axis_conversion(
	            to_forward=self.axis_forward,
	            to_up=self.axis_up,
	        ).to_4x4()

        self.converter.export_ctx.axis_mat = axis_mat
        # Add IDs to all base plugins (shape, emitter, sensor...)
        self.converter.export_ctx.export_ids = self.export_ids

        self.converter.use_selection = self.use_selection

        # Set path to scene .xml file
        self.converter.set_path(self.filepath, split_files=self.split_files)

        window_manager = context.window_manager

        deps_graph = context.evaluated_depsgraph_get()
        deps_graph.update()

        total_progress = len(deps_graph.object_instances)
        window_manager.progress_begin(0, total_progress)

        self.converter.scene_to_dict(deps_graph, window_manager)
        # Write data to scene .xml file
        self.converter.dict_to_xml()
        # Write auxiliary output data to .yml file
        self.converter.aux_dict_to_yml()

        window_manager.progress_end()

        #NOTE: what's the point of this if using baked envmap?
        if not is_envmap and realsky_enabled:
            realsky_names = ["cirrus", "cirrocumulus", "altostratus", "altostratus_mist", "altostratus_billboard", "cumulus", "cumulus_mist", "cumulus_billboard"]
            for obj in scene.objects:
                if obj.name in realsky_names:
                    obj.hide_render = False

        self.report({'INFO'}, "Scene exported successfully!")

        # Reset the exporter
        self.reset()

        return {'FINISHED'}



def menu_export_func(self, context):
    self.layout.operator(ExportMitsuba.bl_idname, text="Mitsuba (.xml)")

def menu_custom_export_func(self, context):
    self.layout.operator(ExportMitsubaExtended.bl_idname, text="Mitsuba (.xml) with Aux Data (.yml)")

def menu_import_func(self, context):
    self.layout.operator(ImportMitsuba.bl_idname, text="Mitsuba (.xml)")

def menu_yml_import_func(self, context):
    self.layout.operator(ImportYMLConfig.bl_idname, text="Custom Config (.yml)")


classes = (
    ImportMitsuba,
    ImportYMLConfig,
    ExportMitsuba,
    ExportMitsubaExtended
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.TOPBAR_MT_file_export.append(menu_export_func)
    bpy.types.TOPBAR_MT_file_export.append(menu_custom_export_func)
    bpy.types.TOPBAR_MT_file_import.append(menu_import_func)
    bpy.types.TOPBAR_MT_file_import.append(menu_yml_import_func)

    # Register HDRI converter
    hdri_converter.register()

def unregister():
    # Unregister HDRI converter
    hdri_converter.unregister()

    for cls in classes:
        bpy.utils.unregister_class(cls)

    bpy.types.TOPBAR_MT_file_export.remove(menu_export_func)
    bpy.types.TOPBAR_MT_file_export.append(menu_custom_export_func)
    bpy.types.TOPBAR_MT_file_import.remove(menu_import_func)
    bpy.types.TOPBAR_MT_file_import.append(menu_yml_import_func)
