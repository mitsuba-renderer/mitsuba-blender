# HDRI Converter - UI Guide

## Panel Location in Blender

```
┌─────────────────────────────────────────┐
│  Blender Interface                      │
│                                         │
│  Properties Panel (Right Side)          │
│  ├── Active Tool and Workspace         │
│  ├── Scene Properties                  │
│  ├── Render Properties  ← HERE         │
│  │   ├── Render Engine                 │
│  │   ├── Sampling                      │
│  │   ├── ...                           │
│  │   └── HDRI Converter  ← PANEL      │
│  ├── Output Properties                 │
│  └── ...                               │
└─────────────────────────────────────────┘
```

## HDRI Converter Panel Layout

```
┌────────────────────────────────────────────┐
│ ▼ HDRI Converter                           │
├────────────────────────────────────────────┤
│                                            │
│  [🌍] Convert Scene to HDRI Map            │
│                                            │
│  ┌──────────────────────────────────────┐ │
│  │ [📷] Camera Setup:                   │ │
│  │  1. Position camera at desired center│ │
│  │  2. Camera will be set to panoramic  │ │
│  │  3. Rotation will be leveled auto    │ │
│  └──────────────────────────────────────┘ │
│                                            │
│  ┌──────────────────────────────────────┐ │
│  │ [🎬] Render Settings:                │ │
│  │  • Engine: Cycles (GPU)              │ │
│  │  • Format: Equirectangular           │ │
│  │  • Aspect Ratio: 2:1                 │ │
│  └──────────────────────────────────────┘ │
│                                            │
│  ┌──────────────────────────────────────┐ │
│  │                                      │ │
│  │        📸 Render HDRI                │ │
│  │                                      │ │
│  └──────────────────────────────────────┘ │
│                                            │
│  ┌──────────────────────────────────────┐ │
│  │ [ℹ️] Notes:                           │ │
│  │  • Position your camera first        │ │
│  │  • Output: .hdr or .exr format       │ │
│  │  • Captures full 360° view           │ │
│  └──────────────────────────────────────┘ │
│                                            │
└────────────────────────────────────────────┘
```

## File Browser Dialog (After Clicking Button)

```
┌─────────────────────────────────────────────────────┐
│  Render HDRI                                     ✕  │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Path: [/path/to/save/folder/           ] [📁]    │
│                                                     │
│  ┌─────────────────────────────────────────────┐  │
│  │  File Browser                               │  │
│  │  ├─ 📁 Desktop                              │  │
│  │  ├─ 📁 Documents                            │  │
│  │  ├─ 📁 Downloads                            │  │
│  │  └─ 📁 ...                                  │  │
│  └─────────────────────────────────────────────┘  │
│                                                     │
│  File Name: [my_hdri.exr              ]           │
│                                                     │
│  ┌─────────────────────────────────────────────┐  │
│  │ Settings:                                   │  │
│  │                                             │  │
│  │  Resolution:  [ 4K (4096x2048)     ▼]      │  │
│  │               ├─ 2K (2048x1024)            │  │
│  │               ├─ 4K (4096x2048)   ← Default│  │
│  │               ├─ 8K (8192x4096)            │  │
│  │               └─ 16K (16384x8192)          │  │
│  │                                             │  │
│  │  Format:      [ OpenEXR (.exr)     ▼]      │  │
│  │               ├─ Radiance HDR (.hdr)       │  │
│  │               └─ OpenEXR (.exr)   ← Default│  │
│  │                                             │  │
│  │  Samples:     [ 512                ]       │  │
│  │               (Range: 1 - 8192)            │  │
│  │                                             │  │
│  └─────────────────────────────────────────────┘  │
│                                                     │
│              [ Cancel ]    [ Render HDRI ]         │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## Workflow Visualization

```
┌──────────────┐
│   Step 1:    │
│   Position   │ → User manually positions camera
│   Camera     │   at desired center point
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Step 2:    │
│   Open       │ → Navigate to Render Properties
│   Panel      │   Find HDRI Converter panel
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Step 3:    │
│   Click      │ → Click "Render HDRI" button
│   Button     │   File browser opens
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Step 4:    │
│   Configure  │ → Choose resolution, format, samples
│   Settings   │   Select save location
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Step 5:    │
│   Automatic  │ → Script configures everything:
│   Setup      │   • Camera → Panoramic/Equirectangular
│              │   • Engine → Cycles + GPU
│              │   • Output → 2:1 ratio + HDR format
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Step 6:    │
│   Render     │ → Blender renders the scene
│   & Save     │   Saves to specified file
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Done!      │
│   HDRI       │ → File ready to use as
│   Ready      │   environment map/IBL
└──────────────┘
```

## Settings Details Diagram

```
Resolution Setting
─────────────────────────────────────────
  2K  → 2048  × 1024  (1:1 ratio)
  4K  → 4096  × 2048  (2:1 ratio) ⭐ Default
  8K  → 8192  × 4096  (2:1 ratio)
  16K → 16384 × 8192  (2:1 ratio)

Format Setting
─────────────────────────────────────────
  Radiance HDR (.hdr)
    ├─ RGB Float
    ├─ Industry standard
    └─ Wide compatibility

  OpenEXR (.exr) ⭐ Default
    ├─ RGB 32-bit float
    ├─ ZIP compression
    ├─ Professional format
    └─ Best quality

Samples Setting
─────────────────────────────────────────
  Low    (256-512)   → Fast, use denoising
  Medium (512-1024)  → Balanced ⭐ Default: 512
  High   (1024-2048) → High quality
  Ultra  (2048+)     → Maximum quality
```

## Camera Configuration Diagram

```
Before (User Positioned)          After (Auto-Configured)
─────────────────────            ─────────────────────────

Camera Position: (x, y, z)       Camera Position: (x, y, z)
Camera Type: Perspective         Camera Type: PANO ✓
Rotation: (any)                  Rotation: (90°, 0°, 0°) ✓
                                 Panorama: Equirectangular ✓
                                 
┌───────────┐                    ┌───────────────────────┐
│ Regular   │                    │ 360° Panoramic View   │
│ Camera    │                    │ Equirectangular       │
│ View      │  ───────────→      │ 2:1 Aspect            │
│ (Rect)    │  Auto Config       │ HDRI Ready            │
└───────────┘                    └───────────────────────┘
```

## Render Process Flow

```
User Click
    │
    ▼
┌────────────────────────────────────────┐
│ RENDER_OT_convert_to_hdri Operator    │
├────────────────────────────────────────┤
│                                        │
│  1. _setup_camera()                   │
│     └─ Get active camera              │
│                                        │
│  2. _configure_camera_panoramic()     │
│     ├─ Set type to PANO               │
│     ├─ Set panorama to Equirectangular│
│     └─ Level rotation                 │
│                                        │
│  3. _setup_render_engine()            │
│     ├─ Set engine to Cycles           │
│     ├─ Enable GPU                     │
│     ├─ Set samples                    │
│     └─ Enable denoising               │
│                                        │
│  4. _setup_output_settings()          │
│     ├─ Set resolution (2:1)           │
│     ├─ Set format (HDR/EXR)           │
│     └─ Set color depth (32-bit)       │
│                                        │
│  5. _render_and_save()                │
│     ├─ Set output path                │
│     ├─ Call bpy.ops.render.render()   │
│     └─ Save to file                   │
│                                        │
└────────────────────────────────────────┘
    │
    ▼
HDRI File Saved
```

## Integration in Add-on Structure

```
mitsuba-blender/
├── __init__.py
├── io/
│   ├── __init__.py ──────────┐
│   ├── hdri_converter.py ◄───┤ Import & Register
│   ├── exporter/             │
│   ├── importer/             │
│   └── ...                   │
├── engine/                   │
└── ...                       │
                              │
Registration Flow:            │
io.register() ────────────────┘
  └─ hdri_converter.register()
       ├─ Register RENDER_OT_convert_to_hdri
       └─ Register RENDER_PT_hdri_converter
```

## User Experience Flow

```
┌─────────────────────────────────────────────────┐
│ User wants to create HDRI from scene           │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
         ┌───────────────┐
         │ Positions     │
         │ camera        │
         └───────┬───────┘
                 │
                 ▼
         ┌───────────────┐       ┌──────────────┐
         │ Opens Render  │       │ Sees panel   │
         │ Properties    │──────→│ with info    │
         └───────┬───────┘       └──────────────┘
                 │
                 ▼
         ┌───────────────┐       ┌──────────────┐
         │ Clicks big    │       │ File browser │
         │ Render button │──────→│ opens        │
         └───────┬───────┘       └──────────────┘
                 │
                 ▼
         ┌───────────────┐       ┌──────────────┐
         │ Chooses       │       │ Confirms     │
         │ settings      │──────→│ and renders  │
         └───────┬───────┘       └──────────────┘
                 │
                 ▼
         ┌───────────────┐       ┌──────────────┐
         │ Waits for     │       │ Gets HDRI    │
         │ render        │──────→│ file         │
         └───────────────┘       └──────────────┘
                                         │
                                         ▼
                                 ┌──────────────┐
                                 │ Uses HDRI as │
                                 │ environment  │
                                 └──────────────┘
```

---

**Legend:**
- 🌍 = World/HDRI icon
- 📷 = Camera icon
- 🎬 = Render icon
- ℹ️ = Info icon
- ⭐ = Default/Recommended
- ✓ = Configured automatically
- → = User action/flow
- ▼ = Dropdown menu
