# Surat Diamond Bourse — Gujarat, India

**Editable Blender Reconstruction**

A reference-led 3D visualization of Surat Diamond Bourse in Surat, Gujarat, India. The project includes the complete editable building scene, selected public interiors, landscaping, two connected basement parking levels, materials, and modelling source files.

The project's original modelling contribution is dedicated under **CC0 1.0 Universal**. No credit to the model creator is requested. See [RIGHTS.md](RIGHTS.md) for the scope of that dedication and the unresolved rights in the real-world architectural design.

![Exterior overview](previews/hero.png)

## Download and open

**[Download the complete model (v1.0.0)](https://github.com/gitfalconhub/surat-diamond-bourse-gujarat-india/releases/download/v1.0.0/surat-diamond-bourse-model-v1.0.0.zip)** · [All downloads and checksums](https://github.com/gitfalconhub/surat-diamond-bourse-gujarat-india/releases/tag/v1.0.0)

Download `surat-diamond-bourse-model-v1.0.0.zip` from the link above. Extract the ZIP and open **`Surat Diamond Bourse.blend`** in Blender **5.2 or newer**. Blender 5.2.1 was used to save and verify the source scene. Compatibility with older Blender versions has not been checked.

The model ZIP includes the six packed texture maps and editable texture copies. No paid assets or third-party add-ons are required. Start in Solid or Material Preview mode to explore the scene; rendering is more demanding. The original Mac GPU preferences are not a requirement: select a rendering device appropriate to your machine.

An optional **`surat-diamond-bourse-showcase-v1.0.0.zip`** adds the separate animated camera scene. This archived camera sequence is 70 seconds, 30 fps, 2,100 frames, with 14 shots and day/dusk lighting. It is a Blender scene, not a finished movie. Its saved presentation resolution is 2560 × 1440; adjust output settings for your own use. It is independent of the ongoing production render.

## What is modelled

- Nine office wings linked by a central spine, with separately editable tower roots.
- Diamond Club, selected public halls, circulation spaces, one representative office fitout, and landscaped courts.
- Two basement parking levels, connecting ramps, lift/stair circulation, procedural vehicles and furniture.
- Procedural geometry and shaders, plus six CC0 texture maps.
- Static presentation cameras and an optional animated camera sequence.

Move the `Tower … Root` empties to reposition a tower. Repeated components may share mesh data; make a mesh single-user before changing only one instance. The `Polish |` collections contain refinement work. Save edits in your own copy.

## Accuracy and limitations

This is an independent visualization assembled from public references. It is **not an official model, a surveyed replica, an as-built BIM, or construction documentation**. Dimensions, façade details, planting, furnishings, parking layout, services, and several interior routes are approximate or inferred. Most tenant offices are represented by exterior masses. The surrounding site is representative rather than a cadastral survey.

See [REFERENCES.md](REFERENCES.md) for source links and modelling assumptions. Reference photographs and drawings themselves are not distributed in this release or used as projected building textures.

## Source and contributions

The `scripts/` folder contains the procedural modelling modules and camera builder. They are supplied for inspection and adaptation inside Blender. The saved `.blend` is the authoritative finished scene: the historical scripts are not a single-command reproduction of every finishing edit. `build_sdb.py` rebuilds scene objects and can write files and render images; run it only in a disposable copy. The included `job.json` disables automatic still rendering for source experimentation.

The model and included textures are in the downloadable model package. Download checksums are supplied with the releases. Improvements to geometry, portability, documentation, or fidelity are welcome through issues or pull requests.

## Licensing

- **Original model data, original documentation, and project preview renders:** CC0 1.0 Universal, to the extent the project contributors hold rights. See [LICENSE](LICENSE) and [RIGHTS.md](RIGHTS.md).
- **Python code, including Python text blocks embedded in the `.blend` files:** GNU GPL 3.0 or later, provided separately from the artwork licence. See [LICENSE-SCRIPTS](LICENSE-SCRIPTS).
- **Grass/leaf-litter texture files:** CC0 from their respective asset creators. See [ASSET_LICENSES.md](ASSET_LICENSES.md).

The CC0 dedication does not waive or license third-party rights in the building's architectural design, names, or trademarks. No affiliation or endorsement by Surat Diamond Bourse or Morphogenesis is claimed. The files are supplied as-is, without warranties.

![Courtyard](previews/courtyard.png)

![Lobby](previews/lobby.png)

![Office](previews/office.png)

![Basement parking](previews/parking.png)
