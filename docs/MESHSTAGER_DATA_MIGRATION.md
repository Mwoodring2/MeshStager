# MeshStager Data Migration Strategy

**Product rename:** Roundup → MeshStager  
**Goal:** Zero user data loss for settings, layouts, tags, favorites, caches, bridge outputs, and logs.

## What moves

| Store | Legacy location | New location |
|-------|-----------------|--------------|
| User data root | `%LOCALAPPDATA%\Roundup\` | `%LOCALAPPDATA%\MeshStager\` |
| QSettings | `HKCU\Software\WoodringTools\Roundup` (Windows registry) | `HKCU\Software\WoodringTools\MeshStager` |
| Tags DB | `…\Roundup\cache\asset_tags.sqlite` | `…\MeshStager\cache\asset_tags.sqlite` |
| Favorites DB | `…\Roundup\cache\asset_favorites.sqlite` | `…\MeshStager\cache\asset_favorites.sqlite` |
| Metadata cache | `…\Roundup\cache\` (SQLite + sidecars) | Same relative paths under MeshStager |
| Bridge outputs | `…\Roundup\bridge\` | `…\MeshStager\bridge\` |
| Logs / exports | `…\Roundup\logs\`, `exports\` | `…\MeshStager\logs\`, `exports\` |

Database **schemas and filenames are unchanged** — only the parent directory and QSettings scope change.

## Implementation

Module: `meshcorral/app/data_migration.py`  
Invoked from: `meshcorral/app/config.py` during `USER_DATA_DIR` initialization (before logging and services start).

### Filesystem migration

1. If `%LOCALAPPDATA%\MeshStager\` **does not exist** and `%LOCALAPPDATA%\Roundup\` **exists** → full `copytree` from Roundup to MeshStager.
2. If **both exist** → merge: copy files/subdirectories from Roundup that are **missing** in MeshStager (never overwrite newer MeshStager files).
3. Legacy Roundup directory is **not deleted** (rollback-safe).

### QSettings migration

1. Open legacy scope `WoodringTools / Roundup`.
2. Open new scope `WoodringTools / MeshStager`.
3. If migration marker `branding/migrated_from_roundup` is absent:
   - Copy each legacy key missing from the new scope.
   - Set migration marker and sync.
4. Legacy registry entries remain on disk.

### Resolution order (runtime)

```
MeshStager USER_DATA_DIR (post-migration)
  ↑
Legacy Roundup copy/merge (one-time)
  ↑
Fresh MeshStager directory (new installs)
```

Settings, layouts, tags, and favorites services continue to use `USER_DATA_DIR` and `SettingsService.APP_NAME` — no call-site changes required after migration runs.

## Verification

Automated: `meshcorral/tests/test_data_migration.py`

Manual checklist:

1. Install/use Roundup with tags, favorites, custom layout, and thumbnail cache populated.
2. Launch MeshStager build.
3. Confirm `%LOCALAPPDATA%\MeshStager\` contains migrated cache/bridge data.
4. Confirm Settings, layout, tags, and favorites match pre-migration behavior.
5. Confirm `%LOCALAPPDATA%\Roundup\` still present (not deleted).

## Rollback

If needed, users can rename directories back or clear `branding/migrated_from_roundup` in the MeshStager QSettings scope. Legacy Roundup data is preserved until manually removed.
