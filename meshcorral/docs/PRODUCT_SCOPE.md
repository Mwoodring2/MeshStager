# Roundup Product Scope

## v1

- scan a **source** (any folder or drive root) for supported 3D-related files
- use the most recent scan as the current working set
- filter scanned results by:
  - text
  - file type category
  - exact extension
  - parent folder name
- multi-select results
- choose a destination folder
- preview a **move** or **copy** plan, then run it safely
- **move** or **copy to destination** (flat filenames, same collision rules for both)
- export current scanned view to CSV

## Workflow

Roundup is scan-first:

1. choose a source (folder or drive root)
2. scan it
3. refine the scanned results with lightweight filters
4. select files
5. choose destination
6. move or copy to destination safely

## Supported file types in v1

Roundup v1 supports these categories by default:

- geometry files
- DCC/source files
- support files tied to 3D assets
- custom pipeline extensions

Examples include:

- geometry: `.stl`, `.obj`, `.fbx`, `.glb`, `.usd`
- DCC/source: `.blend`, `.ztl`, `.ma`, `.mb`, `.max`
- support: `.mtl`, `.json`, `.xml`

Textures are intentionally excluded by default in v1 to reduce scan noise.

## Filtering in v1

Roundup v1 supports lightweight filtering by:

- search text
- exact extension
- file type category
- folder/parent: filter by the immediate parent folder name of each file (for example a project or asset subfolder), not the full path

File type categories: **All**, **Geometry**, **DCC**, **Support**, and **Custom** (each category limits which extensions can appear; the **Ext** filter can still narrow further).

## Not in v1

- ML
- metadata-heavy geometry extraction
- GPU viewer
- smart renaming
- cloud features
- plugins
