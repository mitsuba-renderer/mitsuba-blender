# HDRI Converter for Mitsuba-Blender Add-on

This feature allows you to convert any Blender scene into an equirectangular HDRI (High Dynamic Range Image) map via a single UI button.

## Features

- Automatic camera configuration for 360° panoramic capture
- Equirectangular projection for standard HDRI format
- Support for both Radiance HDR (.hdr) and OpenEXR (.exr) formats
- Multiple resolution presets (2K, 4K, 8K, 16K)
- Automatic Cycles render engine configuration with GPU acceleration
- Built-in denoising for cleaner results

## How to Use

### Quick Start

1. **Position Your Camera**
   - Select or create a camera in your scene
   - Move it to the exact position where you want the center of the HDRI to be
   - The script will automatically level the camera rotation

2. **Access the HDRI Converter Panel**
   - Go to the **Render Properties** tab (Camera icon in Properties panel)
   - Scroll down to find the **"HDRI Converter"** panel
   - The panel may be collapsed by default - click to expand it

3. **Render HDRI**
   - Click the **"Render HDRI"** button
   - Choose your desired settings in the file browser:
     - **Resolution**: Select from 2K, 4K, 8K, or 16K
     - **Format**: Choose between Radiance HDR (.hdr) or OpenEXR (.exr)
     - **Samples**: Set render quality (default: 512)
   - Choose where to save the file
   - Click **"OK"** to start rendering. Once the render is complete, it will be saved to the selected location.

### What the Script Does Automatically

The HDRI converter will automatically configure:

1. **Camera Settings**
   - Adds camera to origin with rotation leveled to the horizon
   - Type: Changed to Panoramic
   - Panorama Type: Set to Equirectangular

2. **Render Engine**
   - Engine: Set to Cycles
   - Device: GPU Compute (if available)
   - Samples: As specified (default 512)
   - Denoising: Enabled

3. **Output Settings**
   - Resolution: 2:1 aspect ratio (e.g., 4096×2048 for 4K)
   - File Format: HDR or EXR with proper color depth
   - Color Depth: Float (Full) for high dynamic range

4. **Rendering**
   - Automatically renders the scene
   - Saves to the specified file path

## Resolution Guide

| Preset | Resolution | Use Case |
|--------|-----------|----------|
| 2K | 2048×1024 | Quick previews, testing |
| 4K | 4096×2048 | Standard quality, most uses |
| 8K | 8192×4096 | High quality, detailed scenes |
| 16K | 16384×8192 | Ultra quality, professional work |

## Output Formats

### Radiance HDR (.hdr)
- Industry-standard HDRI format
- Widely supported
- Good for general use

### OpenEXR (.exr)
- Professional format
- Better compression
- More flexible for compositing
- Recommended for high-quality work

## Tips for Best Results

2. **Lighting**
   - The HDRI will capture all lighting in your scene
   - Make sure your scene has proper lighting setup
   - HDRIs are often used as environment maps, so bright light sources work well

3. **Render Samples**
   - 512-1024 samples usually sufficient for clean results
   - Use higher samples (2048+) for very detailed or noisy scenes
   - Denoising is enabled by default to help with lower sample counts

4. **Scene Considerations**
   - Remove or hide objects very close to the camera
   - HDRIs capture everything in 360°, so consider what's behind the camera too
   - For environment maps, you might want an empty scene with just lighting

## Technical Details

- **Aspect Ratio**: 2:1 (width:height) for proper equirectangular projection
- **Projection**: Equirectangular (lat/long mapping)
- **Color Space**: Linear RGB with high dynamic range
- **Bit Depth**: 32-bit float (EXR) or auto (HDR)

## Troubleshooting

**Render is too dark/bright**
- Check your scene lighting
- HDRIs capture actual light values, not just colors
- Adjust light intensities in your scene

**Render takes too long**
- Reduce sample count (try 256 or 512)
- Use lower resolution for testing
- Enable GPU rendering in Blender preferences

**Output file format issues**
- Make sure you have write permissions to the save location
- The script will automatically add the correct file extension

## Using Your HDRI

Once rendered, you can use your HDRI as:
- Environment map in Blender (World > Environment Texture)
- Background lighting in any 3D software
- IBL (Image-Based Lighting) source
- Reflection map

To use in Blender:
1. Go to Shading workspace
2. Switch to World shading
3. Add Image Texture node
4. Load your rendered HDRI
5. Connect to Background shader


## Technical Details
### Files
1. **`mitsuba-blender/io/hdri_converter.py`** - Main implementation
   - `RENDER_OT_convert_to_hdri` - Operator class that handles the conversion
   - `RENDER_PT_hdri_converter` - UI Panel in Render Properties
   
   
2. **`examples/hdri_converter_example.py`** - Example scripts
---

**Note**: This tool is part of the Mitsuba-Blender add-on and requires Blender 4.0 or higher with Cycles render engine.
