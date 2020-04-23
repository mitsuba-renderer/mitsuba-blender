Mitsuba2 Blender Add-On
=======================

Author: Baptiste Nicolet.

This Add-on allows to export a Blender scene to Mitsuba 2's file format.
Only basic mesh, material, camera and light export are currently supported.

## How to install the Add-on

### In Blender:
- Download this repository as a `zip` archive.
- In Blender, go to **Edit** -> **Preferences** -> **Add-ons** -> **Install**
- Select the downloaded archive
- Enable the Add-on:
	- If PYTHONPATH is not set, specify the path to Mitsuba's python libraries under `python_path`. This should point to the directory conatining **enoki** and **mitsuba** python libraries (Usually something like `/path/to/mitsuba/build/dist/python/`)

### Installing the Add-on from the repository:
If you want to update regularly from the repository, you can create a symbolic link to the repository in the *addons* folder of Blender. Using Ubuntu, it looks like: `ln -s /path/to/cloned/repo ~/.config/blender/2.28x/scripts/addons/mitsuba-blender`

## How to use the Add-on

The current scene can be exported as a Mitsuba 2 scene under **File** -> **Export** -> **Mitsuba 2**

