# HDRI Converter - Quick Reference

## 🚀 Quick Start (3 Steps)

1. **Position Camera** → Place your camera where you want the HDRI center
2. **Open Panel** → Render Properties → "HDRI Converter" panel
3. **Click Button** → "Render HDRI" → Choose settings → Save

---

## 📍 Panel Location

```
Properties Panel → Render Properties (Camera Icon) → Scroll to "HDRI Converter"
```

---

## ⚙️ Settings

### Resolution Options
- **2K** (2048×1024) - Quick preview
- **4K** (4096×2048) - Standard quality ⭐
- **8K** (8192×4096) - High quality
- **16K** (16384×8192) - Ultra quality

### Output Formats
- **OpenEXR (.exr)** - Recommended for professional work ⭐
- **Radiance HDR (.hdr)** - Standard HDRI format

### Samples
- **256-512** - Fast, good with denoising
- **1024** - Standard quality ⭐
- **2048+** - High quality, slower

---

## 🔧 What Gets Configured Automatically

| Setting | Value |
|---------|-------|
| Camera Type | Panoramic |
| Panorama Type | Equirectangular |
| Camera Rotation | Leveled (90°, 0°, 0°) |
| Render Engine | Cycles |
| GPU | Enabled (if available) |
| Denoising | Enabled |
| Aspect Ratio | 2:1 (width:height) |
| Color Depth | 32-bit Float |

---

## 💡 Pro Tips

✅ **DO**
- Position camera at scene center
- Use 512-1024 samples for most cases
- Enable GPU in Blender preferences
- Use OpenEXR for best quality
- Test with 2K before rendering 8K+

❌ **DON'T**
- Place camera inside geometry
- Use extremely high samples unnecessarily
- Forget to save your work before rendering
- Use PNG/JPEG formats (won't work for HDR)

---

## 🎯 Common Use Cases

### Environment Map
1. Create empty scene with lights only
2. Add camera at center
3. Render as 4K HDRI
4. Use as world environment texture

### IBL (Image-Based Lighting)
1. Set up your scene lighting
2. Render from lighting center point
3. Use in other 3D applications

### 360° Scene Capture
1. Position camera in room center
2. Add all lighting
3. Render high-res HDRI
4. Use for realistic lighting

---

## 🔨 Programmatic Usage

```python
import bpy

# Simple usage
bpy.ops.render.convert_to_hdri('INVOKE_DEFAULT')

# With custom settings
bpy.ops.render.convert_to_hdri(
    filepath='/tmp/my_hdri.exr',
    resolution='8192',
    output_format='OPEN_EXR',
    samples=1024
)
```

---

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| "No camera found" | Add camera: Shift+A → Camera |
| Render too dark | Increase light intensity in scene |
| Render too slow | Reduce samples or resolution |
| File won't save | Check write permissions |
| Horizon is tilted | Camera rotation is auto-leveled |

---

## 📊 Render Time Estimates*

| Resolution | Samples | Approx. Time (GPU) |
|-----------|---------|-------------------|
| 2K | 512 | 1-2 min |
| 4K | 512 | 3-5 min |
| 4K | 1024 | 5-10 min |
| 8K | 1024 | 15-30 min |
| 16K | 2048 | 1-2 hours |

*Times vary based on scene complexity and hardware

---

## 🎨 Using Your HDRI in Blender

### As Environment Map
1. Switch to Shading workspace
2. Click "World" button
3. Add Image Texture node (Shift+A)
4. Load your HDRI file
5. Connect to Background shader

### World Shader Nodes
```
Image Texture → Background → World Output
(load your HDRI)
```

---

## 📦 Technical Specs

- **Projection**: Equirectangular (lat/long)
- **Color Space**: Linear RGB
- **Bit Depth**: 32-bit float (full HDR)
- **Aspect Ratio**: 2:1 (mandatory)
- **Coordinate System**: Standard spherical

---

## 🔗 Related Documentation

- Full Guide: `HDRI_CONVERTER_README.md`
- Implementation Details: `HDRI_IMPLEMENTATION_SUMMARY.md`
- Code Examples: `examples/hdri_converter_example.py`

---

## ℹ️ Support

For issues or questions:
- Check the full README
- Review troubleshooting section
- Test with simple scene first
- Verify Blender version (4.0+)

---

**Version**: 1.0  
**Add-on**: Mitsuba-Blender  
**Blender**: 4.0+
