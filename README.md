![Addon Banner](res/banner.jpg)

# Mitsuba Blender+ Add-on

This add-on integrates the Mitsuba renderer into Blender with extended features.

## Main Features

* **Mitsuba scene import**: Import Mitsuba XML scenes and YML scene descriptions in Blender to edit and preview them. Materials are converted to Cycles shader node trees. Mark textures and cameras for use in downstream optimization. 

* **Mitsuba scene export**: Export a Blender scene to a Mitsuba XML scene for rendering. Optionally export with auxiliary information (e.g. marked textures and cameras) YML file for downstream use.

More in-depth information about the features of the original Mitsuba Blender add-on are available on the [wiki](https://github.com/mitsuba-renderer/mitsuba-blender/wiki). Additional features as part of Mitsuba Blender+ are described in "New Custom Features" section below.

## Installation

Mitsuba-Blender+ (Live Development Installation):
1. `git clone` the repo to a working directory.
2. Add the package directory as a symlink to Blender's addons directory. NOTE: we are linking the `mitsuba-blender` directory *inside* the project root, not the whole repo. Symlinking allows us to make changes to the package and have them immediately reflect after restarting Blender for faster iteration. Blender's third-party(user installed) add-ons are stored in [these locations](https://blender.stackexchange.com/a/293148):

Windows: `%appdata%\Blender Foundation\Blender\4.2\scripts\addons\`

Linux: `$HOME/.config/blender/4.2/scripts/addons/`

Mac OS: `/Users/$USER/Library/Application Support/Blender/4.2/scripts/addons/` 

3. In Blender, go to **Edit** -> **Preferences** -> **Add-ons**, find the add-on and enable it.
4. To point the add-on to the Mitsuba dependencies, click on *Install dependencies using pip* to download dependencies.

If you'd like to install the package directly into Blender's add-ons directory instead of symlinking as in Step 2, you can zip the `mitsuba-blender` directory (NOTE: the `mitsuba-blender` directory *inside* the project root, not the whole repo) and then installing the ZIP file as described below:

2. In Blender, go to **Edit** -> **Preferences** -> **Add-ons**. In top right of menu, select drop down arrow and **Install from disk**.
3. Select the downloaded ZIP archive.
4. Find the add-on by sccrolling or using the search bar and enable it.
5. To point the add-on to the Mitsuba dependencies, either click on *Install dependencies using pip* to download the latest package, or check *Use custom Mitsuba path* and browse to your Mitsuba build directory.


## Common issues

:warning: For versions of blender prior to 3.5, you may encounter the error message `Failed to load Mitsuba package` after installing the dependencies via pip. In order to fix that, you need to run blender with the `--python-use-system-env` flag in order for it to correctly pick up the dependencies. In order to do so, find the path to the blender executable, and in a command prompt run:
```
<path_to_blender> --python-use-sytem-env
```

You can refer to the [Installation & Update Guide](https://github.com/mitsuba-renderer/mitsuba-blender/wiki/Installation-&-Update-Guide) on the wiki for more detailed instructions.

Launch Blender from the console in order to see any logged error messages. 

### Supported versions

Blender version should be at least `2.93`. The addon has been extensively tested
on LTS versions of blender (`3.6`, `4.2`). **We recommend using 4.2** whenever
possible.

# Blender-Mitsuba+ Custom Features
## Installation
Follow the Mitsuba-Blender+ (Live Development Installation) instructions above.

## Custom Import: Import YML Configs
Usage: Menu option `File -> Import -> Custom Config (.yml)`

This option allows for importing predefined scene descriptions into Blender. On import, will wipe everything in the current open workspace and replace it with the config contents.

Supports primitive objects, color and image bitmap textures, textured meshes (from obj, stl, ply, fbx file format), environmental maps, lighting, cameras. See `.yml` files in https://github.com/twosixlabs/gard-mit/tree/renderer_nn_module/configs for example configs. 
 
## Custom Export: Export to Mitsuba WITH Auxiliary Optimization Information
Usage: Menu option `File -> Export -> Mitsuba (.xml) with Aux Data (.yml)`

This export option extends the base plugin's Export to Mitsuba feature (`File -> Export -> Mitsuba (.xml)`) by exporting an additional `auxiliary_outputs.yml` file in the same directory as the rest of the scene export. THis file records exportable optimization parameters (currently supports cameras and textures). 

When exporting with the `File -> Export -> Mitsuba (.xml) with Aux Data (.yml)` option, the objects marked as optimizable will be saved into an `auxiliary_outputs.yml` which can be processed downstream by our custom [Differential Renderer module](https://github.com/twosixlabs/gard-mit/blob/renderer_nn_module/src/renderer_module.py).


## Marking scene parameters as optimizable
Currently the plugin supports marking object materials and camaeras for downstream optimizations, e.g. to optimize a patch texture or whether to use a camera or not in a multi-view optimization. 

* To mark as texture or camera as optimizable on import via yml config, add the line

```optimizable: true``` 

to the config for the respective object. E.g.

```
objects:
  - type: MESH
    filepath: "path/to/mesh.obj"
    name: MyMesh
    material:
      name: TexturedMaterial
      shader: BSDF
      texture:
        type: IMAGE
        filepath: "path/to/some/bitmap.png"
        optimizable: true
```

On import into the Blender UI, this property is viewable and editable as a custom property of the object:

- For textures: click on `Material` tab/icon (note: NOT `Object`!) in the right sidebar, scroll down to `Custom Properties` section
- For cameras: with the camera object selected, click on the  `Object` tab/icon in the right sidebar, scroll down to `Custom Properties` section

If not explicitly defined as optimizable in the config, textures and cameras are left as not optimizable by default in the UI. To add the `optimizable` flag to a texture or camera without the field (e.g. user-added object to the scene), you can add the custom property yourself in the appropriate `Custom Properties` section: click `+ New`, edit the property to have type Boolean and name `optimizable`. This will be preserved upon export.
