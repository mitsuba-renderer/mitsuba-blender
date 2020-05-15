Mitsuba 2 Blender Add-On
=======================

Author: Baptiste Nicolet.

This Add-on allows to export a Blender scene to Mitsuba 2's file format.

## How to install the Add-on

### In Blender:
- Download this repository as a `zip` archive.
- In Blender, go to **Edit** -> **Preferences** -> **Add-ons** -> **Install**
- Select the downloaded archive
- Enable the Add-on:
	- If PYTHONPATH is not set, specify the path to Mitsuba's python libraries under `python_path`. This should point to the directory conatining **enoki** and **mitsuba** python libraries (Usually something like `/path/to/mitsuba2/build/dist/python/`)

### Installing the Add-on from the repository:
If you want to update regularly from the repository, you can create a symbolic link to the repository in the *addons* folder of Blender. Using Ubuntu, it looks like: `ln -s /path/to/cloned/repo ~/.config/blender/2.28x/scripts/addons/mitsuba-blender`

## How to use the Add-on

The current scene can be exported as a Mitsuba 2 scene under **File** -> **Export** -> **Mitsuba 2**

## What's supported ?

Currently, this add-on only allows you to save a Blender scene as a Mitsuba 2-compatible scene. Future versions may support more fancy features, such as custom nodes for materials or in-blender rendering.

Export of the following is supported:

- Objects:
  - Meshes
  - Metaballs
  - Text
  - Nurbs surfaces
- Material Nodes:
  - Diffuse BSDF (note: Mitsuba 2 does not handle rough diffuse BSDFs currently)
  - Glossy BSDF
  - Emission BSDF
  - Glass BSDF
  - Image Texture
  - Mix Shader
  - Add Shader (adding two BSDFs is not supported)
- Light Sources:
  - Point Light ::warning: if blender's point light has a radius > 0 renders will be slightly different)
  - Spot Light (:warning: if blender's spot light has a radius > 0 renders will be slightly different)
  - Sun Light
  - Area Light (:warning: Ellipse area maps are not supported)
  - Environment Maps
