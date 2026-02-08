"""
Example script demonstrating how to use the HDRI converter programmatically
This can be run in Blender's Python console or as a script
"""

import bpy

# Example 1: Render HDRI with default settings (4K, OpenEXR)
def render_hdri_default():
    """Render HDRI with default settings"""
    # Make sure we have a camera
    if not bpy.context.scene.camera:
        # Create a camera if none exists
        bpy.ops.object.camera_add(location=(0, 0, 0))
    
    # Call the HDRI converter operator
    bpy.ops.render.convert_to_hdri('INVOKE_DEFAULT')


# Example 2: Render HDRI with custom settings programmatically
def render_hdri_custom(output_path, resolution='8192', samples=1024):
    """
    Render HDRI with custom settings
    
    Args:
        output_path: Full path where to save the HDRI (e.g., '/tmp/my_hdri.exr')
        resolution: Resolution preset ('2048', '4096', '8192', '16384')
        samples: Number of render samples (default: 1024)
    """
    # Make sure we have a camera
    if not bpy.context.scene.camera:
        bpy.ops.object.camera_add(location=(0, 0, 0))
    
    # Call operator with custom parameters
    bpy.ops.render.convert_to_hdri(
        filepath=output_path,
        resolution=resolution,
        output_format='OPEN_EXR',
        samples=samples
    )


# Example 3: Set up a simple scene and render HDRI
def create_scene_and_render_hdri():
    """Create a simple lit scene and render it as HDRI"""
    
    # Clear existing scene
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    
    # Add a sun light
    bpy.ops.object.light_add(type='SUN', location=(0, 0, 10))
    sun = bpy.context.active_object
    sun.data.energy = 5.0
    
    # Add another light for fill
    bpy.ops.object.light_add(type='AREA', location=(5, -5, 5))
    area = bpy.context.active_object
    area.data.energy = 100.0
    area.data.size = 5.0
    
    # Add a camera at the center
    bpy.ops.object.camera_add(location=(0, 0, 0))
    camera = bpy.context.active_object
    bpy.context.scene.camera = camera
    
    # Optional: Add some objects for reflection/environment
    bpy.ops.mesh.primitive_uv_sphere_add(radius=20, location=(0, 0, 0))
    sphere = bpy.context.active_object
    
    # Create emission material for the sphere (sky dome)
    mat = bpy.data.materials.new(name="SkyMaterial")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    
    # Create emission shader
    emission = nodes.new(type='ShaderNodeEmission')
    emission.inputs['Color'].default_value = (0.5, 0.7, 1.0, 1.0)  # Sky blue
    emission.inputs['Strength'].default_value = 1.0
    
    output = nodes.new(type='ShaderNodeOutputMaterial')
    mat.node_tree.links.new(emission.outputs['Emission'], output.inputs['Surface'])
    
    # Assign material to sphere
    if sphere.data.materials:
        sphere.data.materials[0] = mat
    else:
        sphere.data.materials.append(mat)
    
    # Render HDRI
    bpy.ops.render.convert_to_hdri(
        filepath='/tmp/scene_hdri.exr',
        resolution='4096',
        samples=512
    )


# Example 4: Access the panel programmatically
def show_hdri_panel_info():
    """Print information about the HDRI panel"""
    print("HDRI Converter Panel Information:")
    print("  Panel ID: RENDER_PT_hdri_converter")
    print("  Location: Render Properties")
    print("  Operator ID: render.convert_to_hdri")
    print("\nTo access manually:")
    print("  1. Go to Render Properties tab")
    print("  2. Look for 'HDRI Converter' panel")
    print("  3. Click 'Render HDRI' button")


# Usage examples:
if __name__ == "__main__":
    # Uncomment the example you want to run:
    
    # render_hdri_default()
    
    # render_hdri_custom('/tmp/my_hdri.exr', resolution='8192', samples=1024)
    
    # create_scene_and_render_hdri()
    
    show_hdri_panel_info()
