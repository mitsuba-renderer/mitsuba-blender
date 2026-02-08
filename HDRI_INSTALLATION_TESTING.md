# HDRI Converter - Installation & Testing Guide

## Installation

The HDRI converter is now integrated into the Mitsuba-Blender add-on. No separate installation required.

### Requirements
- Blender 4.0 or higher
- Mitsuba-Blender add-on installed
- Cycles render engine (built into Blender)

### Files Added/Modified

#### New Files Created
```
mitsuba-blender/io/hdri_converter.py          - Main implementation
HDRI_CONVERTER_README.md                      - User documentation
HDRI_IMPLEMENTATION_SUMMARY.md                - Technical details
HDRI_QUICK_REFERENCE.md                       - Quick reference card
HDRI_UI_GUIDE.md                              - Visual UI guide
examples/hdri_converter_example.py            - Example usage scripts
```

#### Modified Files
```
mitsuba-blender/io/__init__.py                - Integration with add-on
```

### Verify Installation

1. Open Blender 4.0+
2. Load/reload the Mitsuba-Blender add-on
3. Go to Render Properties
4. Look for "HDRI Converter" panel

If the panel appears, installation is successful! ✅

---

## Testing the Feature

### Test 1: Basic Functionality

**Objective**: Verify the HDRI converter works with default settings

**Steps**:
1. Open Blender
2. Delete default cube (X → Delete)
3. Add a Sun light (Shift+A → Light → Sun)
4. Set Sun energy to 5.0
5. Ensure camera exists (should be default camera)
6. Go to Render Properties → HDRI Converter panel
7. Click "Render HDRI"
8. Choose settings:
   - Resolution: 2K (for fast test)
   - Format: OpenEXR
   - Samples: 256
9. Save to `/tmp/test_hdri.exr`
10. Wait for render to complete

**Expected Result**: 
- Render completes without errors
- File saved to specified location
- File size is reasonable (~2-10 MB for 2K)
- Can be opened in image viewer

---

### Test 2: Camera Configuration

**Objective**: Verify camera is properly configured

**Steps**:
1. Create new scene
2. Add camera (Shift+A → Camera)
3. Select camera
4. Note current camera settings
5. Run HDRI converter (2K, 256 samples)
6. After render, check camera properties

**Expected Result**:
- Camera Type: PANO
- Panorama Type: EQUIRECTANGULAR  
- Rotation: (90°, 0°, 0°) or (1.5708, 0, 0) in radians

**Verification**:
```python
import bpy
cam = bpy.context.scene.camera
print(f"Type: {cam.data.type}")  # Should be 'PANO'
print(f"Panorama: {cam.data.panorama_type}")  # Should be 'EQUIRECTANGULAR'
print(f"Rotation: {cam.rotation_euler}")  # Should be (1.5708, 0, 0)
```

---

### Test 3: Output Formats

**Objective**: Test both HDR and EXR formats

**Steps**:
1. Set up simple lit scene
2. Render HDRI as OpenEXR
   - Save to `/tmp/test.exr`
3. Render HDRI as Radiance HDR
   - Save to `/tmp/test.hdr`
4. Check both files

**Expected Result**:
- Both files created successfully
- EXR file slightly larger (due to 32-bit float)
- Both can be loaded as environment textures in Blender
- Both preserve HDR data (not clamped to 0-1)

**Verification**:
```python
import bpy

# Load as environment texture
world = bpy.data.worlds['World']
world.use_nodes = True
nodes = world.node_tree.nodes
env_tex = nodes.new('ShaderNodeTexEnvironment')
env_tex.image = bpy.data.images.load('/tmp/test.exr')
```

---

### Test 4: Multiple Resolutions

**Objective**: Test different resolution presets

**Steps**:
1. Render same scene at all resolutions:
   - 2K → `/tmp/hdri_2k.exr`
   - 4K → `/tmp/hdri_4k.exr`
   - 8K → `/tmp/hdri_8k.exr`
2. Check file sizes
3. Verify aspect ratios

**Expected Results**:
| Resolution | Expected Size | Aspect Ratio |
|-----------|--------------|--------------|
| 2K | 2048×1024 | 2:1 |
| 4K | 4096×2048 | 2:1 |
| 8K | 8192×4096 | 2:1 |

**Verification**:
```python
import bpy

img = bpy.data.images.load('/tmp/hdri_4k.exr')
print(f"Size: {img.size[0]} × {img.size[1]}")
print(f"Ratio: {img.size[0] / img.size[1]}")  # Should be 2.0
```

---

### Test 5: Render Settings

**Objective**: Verify render engine and settings

**Steps**:
1. Start with scene using EEVEE engine
2. Run HDRI converter
3. Check render settings after operation

**Expected Result**:
- Render Engine: CYCLES
- Device: GPU
- Samples: As specified (e.g., 512)
- Denoising: Enabled

**Verification**:
```python
import bpy

scene = bpy.context.scene
print(f"Engine: {scene.render.engine}")  # 'CYCLES'
print(f"Device: {scene.cycles.device}")  # 'GPU'
print(f"Samples: {scene.cycles.samples}")  # Your chosen value
print(f"Denoising: {scene.cycles.use_denoising}")  # True
```

---

### Test 6: Programmatic Usage

**Objective**: Test calling operator from Python

**Steps**:
1. Open Blender's Python console (Scripting workspace)
2. Run test script:

```python
import bpy

# Ensure camera exists
if not bpy.context.scene.camera:
    bpy.ops.object.camera_add(location=(0, 0, 0))

# Call operator programmatically
bpy.ops.render.convert_to_hdri(
    filepath='/tmp/programmatic_hdri.exr',
    resolution='4096',
    output_format='OPEN_EXR',
    samples=512
)
```

**Expected Result**:
- Renders successfully
- File created at specified path
- No errors in console

---

### Test 7: Error Handling

**Objective**: Test error cases

**Test 7a: No Camera**
```python
import bpy

# Delete all cameras
for obj in bpy.data.objects:
    if obj.type == 'CAMERA':
        bpy.data.objects.remove(obj)

# Try to render HDRI
bpy.ops.render.convert_to_hdri('INVOKE_DEFAULT')
```
**Expected**: Error message "No camera found in scene"

**Test 7b: Invalid Path**
```python
bpy.ops.render.convert_to_hdri(
    filepath='/invalid/path/hdri.exr',
    resolution='2048',
    samples=256
)
```
**Expected**: Graceful error handling or system error

---

### Test 8: UI Panel Visibility

**Objective**: Verify panel appears correctly

**Steps**:
1. Open Blender
2. Go to Render Properties
3. Look for HDRI Converter panel
4. Check panel can be collapsed/expanded
5. Verify all info boxes are visible
6. Check button is prominent and clickable

**Expected Result**:
- Panel appears in Render Properties
- Panel is collapsible
- All text is readable
- Button is large and obvious
- Icons display correctly

---

### Test 9: Real-World Use Case

**Objective**: Create usable HDRI from realistic scene

**Steps**:
1. Create a room with walls
2. Add multiple light sources:
   - Window with sun
   - Ceiling light
   - Practical lamps
3. Add basic furniture (optional)
4. Position camera in room center
5. Render as 4K HDRI with 1024 samples
6. Use resulting HDRI as environment map in new scene

**Expected Result**:
- HDRI captures all lighting
- Can be used as environment map
- Provides realistic lighting when applied
- No visible artifacts or seams

**Usage Verification**:
```python
import bpy

# Use the HDRI in World
world = bpy.data.worlds['World']
world.use_nodes = True
nodes = world.node_tree.nodes
nodes.clear()

env_tex = nodes.new('ShaderNodeTexEnvironment')
env_tex.image = bpy.data.images.load('/tmp/scene_hdri.exr')

background = nodes.new('ShaderNodeBackground')
output = nodes.new('ShaderNodeOutputWorld')

world.node_tree.links.new(env_tex.outputs['Color'], background.inputs['Color'])
world.node_tree.links.new(background.outputs['Background'], output.inputs['Surface'])
```

---

## Performance Benchmarks

Run these tests to establish baseline performance:

```python
import bpy
import time

def benchmark_hdri(resolution, samples):
    start = time.time()
    
    bpy.ops.render.convert_to_hdri(
        filepath=f'/tmp/benchmark_{resolution}_{samples}.exr',
        resolution=resolution,
        output_format='OPEN_EXR',
        samples=samples
    )
    
    elapsed = time.time() - start
    print(f"{resolution} @ {samples} samples: {elapsed:.2f}s")
    return elapsed

# Run benchmarks
benchmark_hdri('2048', 256)
benchmark_hdri('4096', 512)
benchmark_hdri('4096', 1024)
benchmark_hdri('8192', 512)
```

**Record Results**: Document times for your hardware

---

## Troubleshooting Tests

### If HDRI Appears Black
**Test**:
```python
import bpy

# Check if there's any light in scene
lights = [obj for obj in bpy.data.objects if obj.type == 'LIGHT']
print(f"Lights in scene: {len(lights)}")

# Check light energy
for light in lights:
    print(f"{light.name}: {light.data.energy}")
```

### If Panel Doesn't Appear
**Test**:
```python
import bpy

# Check if module is registered
print('RENDER_OT_convert_to_hdri' in dir(bpy.ops.render))
print('RENDER_PT_hdri_converter' in [p.__name__ for p in bpy.types.Panel.__subclasses__()])

# Try manual registration
from mitsuba_blender.io import hdri_converter
hdri_converter.register()
```

### If Render Fails
**Test**:
```python
import bpy

# Check Cycles availability
print(f"Render engine: {bpy.context.scene.render.engine}")
print(f"Available engines: {bpy.context.scene.render.engine_items}")

# Check GPU availability
print(f"Cycles device: {bpy.context.scene.cycles.device}")
```

---

## Automated Test Suite

Create a test script for automated validation:

```python
"""
Automated HDRI Converter Test Suite
Run this in Blender's Python console
"""

import bpy
import os

def setup_test_scene():
    """Create a simple test scene"""
    # Clear scene
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    
    # Add camera
    bpy.ops.object.camera_add(location=(0, 0, 0))
    bpy.context.scene.camera = bpy.context.active_object
    
    # Add light
    bpy.ops.object.light_add(type='SUN', location=(5, 5, 10))
    bpy.context.active_object.data.energy = 5.0

def test_basic_render():
    """Test basic HDRI rendering"""
    print("\n=== Test: Basic Render ===")
    setup_test_scene()
    
    filepath = '/tmp/test_basic.exr'
    bpy.ops.render.convert_to_hdri(
        filepath=filepath,
        resolution='2048',
        samples=128
    )
    
    assert os.path.exists(filepath), "HDRI file not created"
    assert os.path.getsize(filepath) > 1000, "HDRI file too small"
    print("✓ Basic render test passed")

def test_camera_config():
    """Test camera configuration"""
    print("\n=== Test: Camera Configuration ===")
    setup_test_scene()
    
    cam = bpy.context.scene.camera
    bpy.ops.render.convert_to_hdri(
        filepath='/tmp/test_cam.exr',
        resolution='2048',
        samples=128
    )
    
    assert cam.data.type == 'PANO', "Camera not panoramic"
    assert cam.data.panorama_type == 'EQUIRECTANGULAR', "Not equirectangular"
    print("✓ Camera configuration test passed")

def test_resolutions():
    """Test multiple resolutions"""
    print("\n=== Test: Multiple Resolutions ===")
    setup_test_scene()
    
    resolutions = ['2048', '4096']
    for res in resolutions:
        filepath = f'/tmp/test_{res}.exr'
        bpy.ops.render.convert_to_hdri(
            filepath=filepath,
            resolution=res,
            samples=64
        )
        assert os.path.exists(filepath), f"Failed at {res}"
        print(f"✓ {res} resolution passed")

def run_all_tests():
    """Run complete test suite"""
    print("\n" + "="*50)
    print("HDRI Converter Test Suite")
    print("="*50)
    
    try:
        test_basic_render()
        test_camera_config()
        test_resolutions()
        
        print("\n" + "="*50)
        print("✓ All tests passed!")
        print("="*50)
        
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
    except Exception as e:
        print(f"\n✗ Error: {e}")

# Run tests
if __name__ == "__main__":
    run_all_tests()
```

---

## Sign-Off Checklist

Before considering the feature complete, verify:

- [ ] HDRI converter module created (`hdri_converter.py`)
- [ ] Module integrated into io/__init__.py
- [ ] No Python syntax errors
- [ ] Panel appears in Render Properties
- [ ] Button is clickable and opens file browser
- [ ] All resolution presets work
- [ ] Both output formats (HDR/EXR) work
- [ ] Camera configured correctly (panoramic, equirectangular)
- [ ] Render engine set to Cycles
- [ ] GPU enabled if available
- [ ] Output has 2:1 aspect ratio
- [ ] HDR color depth preserved
- [ ] Files save successfully
- [ ] Can be used as environment maps
- [ ] Error handling works (no camera case)
- [ ] Documentation complete
- [ ] Example scripts provided
- [ ] Test suite passes

---

## Version History

### Version 1.0 (2026-02-06)
- Initial implementation
- HDRI converter operator
- UI panel in Render Properties
- Support for 2K, 4K, 8K, 16K resolutions
- HDR and EXR output formats
- Automatic camera, render, and output configuration
- Complete documentation suite

---

**Status**: ✅ Ready for Use  
**Last Updated**: February 6, 2026  
**Blender Version**: 4.0+
