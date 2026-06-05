# MeshStager sample data policy

**Applies to:** GitHub, public sharing, and tester handoff repositories.

---

## Do not commit

- Private production meshes or client deliverables
- Vendor libraries licensed for internal use only
- Large binary archives (`.zip`, `.7z`, folder trees of real project assets)
- Screenshots or exports that expose confidential part names or paths
- `%LOCALAPPDATA%\MeshStager\` caches, SQLite DBs, or bridge job outputs
- `render_cache/`, `thumbnail_cache/`, `staging_cache/`, `logs/`

---

## Acceptable test data

- **Synthetic or trivial** geometry generated locally for QA (small STL/OBJ you create for testing)
- **Public-domain or self-authored** demo files under `meshcorral/tests/fixtures/` if kept tiny (< 1 MB each)
- Path examples in docs using placeholders (`C:\Users\<you>\`, `D:\TestMeshes\`) — not real usernames or drive letters from a specific machine

---

## Large files

GitHub is not a mesh CDN. If sample data is needed:

1. Keep it outside the repo (tester provides their own folder), or
2. Use Git LFS with explicit approval and license review, or
3. Link to a separate approved artifact store in release notes — not in the main tree

---

## Before pushing

```bat
git status --short
git add --dry-run .
```

Reject any accidental `.db`, `.sqlite`, `.blend`, `.fbx`, or multi-MB binaries unless they are approved fixtures.
