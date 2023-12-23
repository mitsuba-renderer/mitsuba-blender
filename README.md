![Addon Banner](res/banner.jpg)

# Mitsuba Blender Add-on

[![Nightly Release](https://github.com/mitsuba-renderer/mitsuba-blender/actions/workflows/nightly_release.yml/badge.svg)](https://github.com/mitsuba-renderer/mitsuba-blender/actions/workflows/nightly_release.yml)

This add-on integrates the Mitsuba renderer into Blender.

## Main Features

* **Mitsuba scene import**: Import Mitsuba XML scenes in Blender to edit and preview them. Materials are converted to Cycles shader node trees.

* **Mitsuba scene export**: Export a Blender scene to a Mitsuba XML scene for rendering.

More in-depth information about the features of the add-on are available on the [wiki](https://github.com/mitsuba-renderer/mitsuba-blender/wiki).

## Installation

- Download the latest release from the [release section](https://github.com/mitsuba-renderer/mitsuba-blender/releases).
- In Blender, go to **Edit** -> **Preferences** -> **Add-ons** -> **Install**.
- Select the downloaded ZIP archive.
- Find the add-on using the search bar and enable it.
- To point the add-on to the Mitsuba dependencies, either click on *Install dependencies using pip* to download the latest package, or check *Use custom Mitsuba path* and browse to your Mitsuba build directory.

## Common issues

:warning: For versions of blender prior to 3.5, you may encounter the error message `Failed to load Mitsuba package` after installing the dependencies via pip. In order to fix that, you need to run blender with the `--python-use-system-env` flag in order for it to correctly pick up the dependencies. In order to do so, find the path to the blender executable, and in a command prompt run:
```
<path_to_blender> --python-use-sytem-env
```

You can refer to the [Installation & Update Guide](https://github.com/mitsuba-renderer/mitsuba-blender/wiki/Installation-&-Update-Guide) on the wiki for more detailed instructions.

### Supported versions

Blender version should be at least `2.93`. The addon has been extensively tested
on LTS versions of blender (`3.3`, `3.6`). We recommend using those whenever
possible.
