"""
HDRI Converter for Blender
Converts a scene into an HDRI map by configuring camera, render settings, and output
"""

import bpy
from bpy.types import Operator, Panel
from bpy.props import IntProperty, EnumProperty, StringProperty
import os


class RENDER_OT_convert_to_hdri(Operator):
    """Convert the current scene to an HDRI map"""
    bl_idname = "render.convert_to_hdri"
    bl_label = "Render HDRI"
    bl_description = "Configure and render the scene as an equirectangular HDRI map"
    bl_options = {'REGISTER', 'UNDO'}

    # Resolution presets
    resolution: EnumProperty(
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

    # Output format
    output_format: EnumProperty(
        name="Format",
        description="Output file format for HDRI",
        items=[
            ('HDR', "Radiance HDR (.hdr)", "Radiance HDR format"),
            ('OPEN_EXR', "OpenEXR (.exr)", "OpenEXR format"),
        ],
        default='OPEN_EXR'
    )

    # File path
    filepath: StringProperty(
        name="File Path",
        description="Path to save the HDRI file",
        subtype='FILE_PATH'
    )

    # Samples
    samples: IntProperty(
        name="Samples",
        description="Number of render samples",
        default=512,
        min=1,
        max=8192
    )

    def invoke(self, context, event):
        """Open file browser when operator is invoked"""
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        """Execute the HDRI conversion and rendering"""
        scene = context.scene
        
        # Step 1: Get or create camera
        camera = self._setup_camera(context)
        if not camera:
            self.report({'ERROR'}, "No camera found in scene. Please add a camera first.")
            return {'CANCELLED'}
        
        # Step 2: Configure camera for 360° capture
        self._configure_camera_panoramic(camera)
        
        # Step 3: Set render engine to Cycles
        self._setup_render_engine(scene)
        
        # Step 4: Set resolution and output format
        self._setup_output_settings(scene)
        
        # Step 5: Render and save
        result = self._render_and_save(context)
        
        if result:
            self.report({'INFO'}, f"HDRI rendered and saved to: {self.filepath}")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Failed to render HDRI")
            return {'CANCELLED'}

    def _setup_camera(self, context):
        """Create a new camera at origin for HDRI rendering"""
        scene = context.scene

        camera_data = bpy.data.cameras.new(name="HDRI_Camera")
        camera_obj = bpy.data.objects.new(name="HDRI_Camera", object_data=camera_data)
        scene.collection.objects.link(camera_obj)

        camera_obj.location = (0.0, 0.0, 0.0)
        camera_obj.rotation_euler[0] = 1.5708  # 90 degrees (X)
        camera_obj.rotation_euler[1] = 0.0     # 0 degrees (Y)
        camera_obj.rotation_euler[2] = -1.5708 # -90 degrees (Z)

        scene.camera = camera_obj
        return camera_obj

    def _configure_camera_panoramic(self, camera):
        """Configure camera for equirectangular panoramic rendering"""
        camera_data = camera.data
        
        # Set camera type to Panoramic
        camera_data.type = 'PANO'
        
        # Set panorama type to Equirectangular
        camera_data.panorama_type = 'EQUIRECTANGULAR'
        # Rotation is set when the camera is created in _setup_camera

    def _setup_render_engine(self, scene):
        """Configure render engine to Cycles"""
        # Set render engine to Cycles
        scene.render.engine = 'CYCLES'
        
        # Use GPU if available
        cycles = scene.cycles
        cycles.device = 'GPU'
        
        # Set samples
        cycles.samples = self.samples
        
        # Enable denoising for cleaner results
        scene.cycles.use_denoising = True

    def _setup_output_settings(self, scene):
        """Configure resolution and output format for HDRI"""
        render = scene.render
        
        # Set resolution (2:1 aspect ratio)
        width = int(self.resolution)
        height = width // 2
        
        render.resolution_x = width
        render.resolution_y = height
        render.resolution_percentage = 100
        
        # CRITICAL: Set color management for HDR output
        # This prevents view transforms from compressing the dynamic range
        scene.display_settings.display_device = 'sRGB'
        scene.view_settings.view_transform = 'Standard'  # Use Standard, not Filmic
        scene.view_settings.look = 'None'
        scene.view_settings.exposure = 0.0
        scene.view_settings.gamma = 1.0
        
        # Set output format
        image_settings = render.image_settings
        image_settings.file_format = self.output_format
        
        # Set color depth to capture high dynamic range
        if self.output_format == 'OPEN_EXR':
            image_settings.color_mode = 'RGB'
            image_settings.color_depth = '32'  # Float (Full)
            image_settings.exr_codec = 'ZIP'  # Compression
        elif self.output_format == 'HDR':
            image_settings.color_mode = 'RGB'
            # HDR format automatically uses float data

    def _render_and_save(self, context):
        """Render the scene and save to file"""
        scene = context.scene
        
        # Determine file extension
        ext = '.exr' if self.output_format == 'OPEN_EXR' else '.hdr'
        
        # Ensure filepath has correct extension
        if not self.filepath.lower().endswith(ext):
            # Remove any existing extension
            base_path = os.path.splitext(self.filepath)[0]
            self.filepath = base_path + ext
        
        # Set output path
        scene.render.filepath = self.filepath
        
        # Render
        bpy.ops.render.render(write_still=True)
        
        return True


class RENDER_PT_hdri_converter(Panel):
    """Panel for HDRI Converter in Render Properties"""
    bl_label = "HDRI Converter"
    bl_idname = "RENDER_PT_hdri_converter"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'render'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        
        layout.label(text="Convert Scene to HDRI Map", icon='WORLD')
        
        box = layout.box()
        box.label(text="Camera Setup:", icon='CAMERA_DATA')
        col = box.column(align=True)
        col.label(text="1. Camera is created at origin (0, 0, 0)")
        col.label(text="2. Rotation set to (90°, 0°, -90°)")
        col.label(text="3. Camera set to panoramic/equirect")
        
        box = layout.box()
        box.label(text="Render Settings:", icon='SCENE')
        col = box.column(align=True)
        col.label(text="• Engine: Cycles (GPU)")
        col.label(text="• Format: Equirectangular")
        col.label(text="• Aspect Ratio: 2:1")
        col.label(text="• Color: Linear (no tone mapping)")
        
        layout.separator()
        
        # Main render button
        row = layout.row()
        row.scale_y = 2.0
        row.operator("render.convert_to_hdri", text="Render HDRI", icon='RENDER_STILL')
        
        layout.separator()
        
        # Additional info
        box = layout.box()
        box.label(text="Notes:", icon='INFO')
        col = box.column(align=True)
        col.label(text="• Existing cameras are ignored")
        col.label(text="• Output: .hdr or .exr format")
        col.label(text="• Captures full 360° view")


# Registration
classes = (
    RENDER_OT_convert_to_hdri,
    RENDER_PT_hdri_converter,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
