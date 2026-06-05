# Favorites (Tier 2.2)

Mark important assets with a star so you can filter the working set to **Favorites Only**.

---

## How to favorite

1. Scan a folder.
2. Select **one** asset.
3. On the **Metadata** tab, click **☆ Favorite** (becomes **★ Favorited**).

Favorites persist in `%LOCALAPPDATA%\MeshStager\cache\asset_favorites.sqlite`.

Upgrading from Roundup: data is migrated automatically from `%LOCALAPPDATA%\Roundup\` on first MeshStager launch (see `docs/MESHSTAGER_DATA_MIGRATION.md`).

---

## Filter

Left column → **Favorites**:

| Value | Shows |
|-------|--------|
| **All** | Every visible row (default) |
| **Favorites Only** | Assets you starred |

Works with search, extension, folder, and tag filters.

---

## Notes

- Favorites do not move or rename files.
- Multi-select does not show the star toggle (single asset only in MVP).
- Tier 2.2 builds on Tier 2.1 tags without changing the Prime v1.0 frozen core.
