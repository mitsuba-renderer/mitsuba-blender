![Addon Banner](res/banner.jpg)

# Mitsuba Blender Add-on

[![Test suite](https://github.com/mitsuba-renderer/mitsuba-blender/actions/workflows/test.yml/badge.svg)](https://github.com/mitsuba-renderer/mitsuba-blender/actions/workflows/test.yml)
[![Nightly Release](https://github.com/mitsuba-renderer/mitsuba-blender/actions/workflows/nightly_release.yml/badge.svg)](https://github.com/mitsuba-renderer/mitsuba-blender/actions/workflows/nightly_release.yml)

This add-on integrates the [Mitsuba](https://github.com/mitsuba-renderer/mitsuba3)
renderer into Blender.

## Main features

* **Render engine**: Select *Mitsuba* as the render engine and press F12 to
  render the current scene with Mitsuba, with progress reporting, cancel
  support and AOV passes.

* **Mitsuba scene export**: Export a Blender scene to a Mitsuba XML scene for
  rendering. Cycles shader node trees are translated to Mitsuba BSDFs,
  textures and emitters.

* **Mitsuba scene import**: Import Mitsuba XML scenes in Blender to edit and
  preview them. Materials are converted to Cycles shader node trees.

## Installation

The add-on is packaged as a Blender **extension** and requires **Blender 4.2
LTS or newer**.

- Download the zip matching your platform from the
  [release section](https://github.com/mitsuba-renderer/mitsuba-blender/releases)
  (a rolling *Nightly Release* tracks the master branch).
- In Blender, go to **Edit** -> **Preferences** -> **Get Extensions**, click
  the dropdown arrow in the top-right corner and choose **Install from
  Disk...**, then select the downloaded zip. Alternatively, drag and drop the
  zip into the Blender window.

The release zips bundle the matching `mitsuba` and `drjit` wheels, so no
further setup is needed. Wheels are included for Python 3.11 (Blender 4.2
through 5.0) and Python 3.13 (Blender 5.1 and newer); Blender deploys the
ones matching its bundled Python. Release builds are available for Linux
(x86-64), Windows (x86-64) and macOS (Apple Silicon); on other platforms,
install the `mitsuba` package into Blender's Python yourself and install the
extension built from source (see below).

To use a self-compiled Mitsuba instead of the bundled one, set *Custom
Mitsuba path* in the add-on preferences to the `python` directory of your
build (it must be compiled against Blender's Python version) and restart
Blender.

## Supported versions

- **Blender**: 4.2 LTS and newer. The test suite runs against the 4.2 and
  4.5 LTS releases on every change, and weekly against Blender's daily
  development build.
- **Mitsuba**: 3.9.0 (bundled with the release zips).

## Feature coverage

Geometry is converted through `mitsuba.Mesh` in both directions: any
mesh-backed Mitsuba shape (`obj`, `ply`, `serialized`, ...) imports as a
Blender mesh, and analytic `sphere`, `rectangle`, `cube` and `disk` shapes map
to Blender primitives. Repeated meshes, collection instances and particle
instances export as Mitsuba `shapegroup`/`instance` pairs. Cameras
(perspective, orthographic, depth of field, lens shift), all Blender light
types and world backgrounds (constant and environment maps) convert in both
directions with matching radiometric units.

### Material export

| Blender node | Mitsuba plugin |
|---|---|
| Principled BSDF | `principled` (+ `mask` for alpha, `area` emitter for emission) |
| Diffuse BSDF | `diffuse` |
| Glossy BSDF | `conductor` / `roughconductor` |
| Glass BSDF | `dielectric` / `thindielectric` / `roughdielectric` |
| Refraction BSDF | `dielectric` / `roughdielectric` (with a warning) |
| Transparent BSDF | `null` / `mask` |
| Translucent BSDF | `principledthin` |
| Emission | `area` emitter |
| Mix Shader | `blendbsdf` / `mask` |
| Add Shader | BSDF + emitter, or summed emitters |
| Holdout | `null` (with a warning) |
| Image Texture | `bitmap` |
| Checker Texture | `checkerboard` |
| Environment Texture | `envmap` (world background) |
| Color Attribute | `mesh_attribute` |
| Normal Map / Bump | `normalmap` / `bumpmap` |
| Mapping / Texture Coordinate | `to_uv` transform |

Value-only subgraphs feeding the nodes above are folded into constants: Math,
Vector Math, Mix, RGB, Value, Invert, Gamma, Brightness/Contrast, Map Range,
Clamp, Separate/Combine XYZ/Color and RGB to BW. Anything outside this subset
produces a warning and a best-effort fallback instead of a failed export.

### Material import

`principled`, `diffuse`, `conductor`, `roughconductor`, `dielectric`,
`thindielectric`, `roughdielectric`, `plastic`, `roughplastic`, `twosided`,
`blendbsdf`, `mask`, `null`, `normalmap`, `bumpmap`, and the `bitmap`,
`checkerboard`, `scale` and `mesh_attribute` textures. Unsupported plugins
import as an error-colored placeholder material, and the import never aborts:
it reports the number of warnings at the end.

## Development setup

Clone the repository and symlink (or copy) the `mitsuba_blender` directory
into Blender's `user_default` extension repository, e.g. on Linux:

```bash
ln -s $(pwd)/mitsuba_blender ~/.config/blender/4.2/extensions/user_default/
```

Then enable *Mitsuba Blender* in the extensions preferences. With no bundled
wheels in the source tree, Mitsuba must be available in Blender's Python:

```bash
/path/to/blender/4.2/python/bin/python3.11 -m pip install mitsuba==3.9.0
```

### Running the tests

The test suite runs with pytest inside headless Blender:

```bash
/path/to/blender/4.2/python/bin/python3.11 -m pip install pytest
export BLENDER=/path/to/blender/blender
python3 tests/run.py            # fast tests
python3 tests/run.py --all      # includes slow and packaging tests
```

Set `MITSUBA_PYTHON=/path/to/mitsuba3/build/python` to run the suite against
a local Mitsuba build instead of the wheel. See `tests/README.md` for the
full harness documentation.

## Release process

- CI (`.github/workflows/test.yml`) runs `tests/run.py --all` on every push
  and pull request and uploads the per-platform extension zips (built by
  `release/build_extension.py`, which bundles the Mitsuba wheels) as an
  artifact.
- Every commit on master updates the *Nightly Release*.
- Pushing a `v*` tag creates a draft release with the same zips. Bump
  `version` in `mitsuba_blender/blender_manifest.toml` first; the Mitsuba
  version is pinned in `release/build_extension.py` and in the CI workflow.
- Each zip bundles mitsuba/drjit wheels for every Python version shipped by
  a supported Blender release (`PYTHON_VERSIONS` in
  `release/build_extension.py`, currently 3.11 and 3.13). When a new Blender
  series moves to another Python version, add it there, provided Mitsuba
  publishes wheels for it; otherwise cap `blender_version_max` in the
  manifest until wheels exist.
