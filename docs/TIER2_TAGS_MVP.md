# Tier 2.1 — Tags MVP

User-defined organization on top of the **Prime v1.0 core freeze**. Tags do not rename files and do not modify scan, thumbnail routing, metadata cache, or queue behavior.

---

## Layout

```
meshcorral/
├── services/tagging/
│   ├── tag_models.py
│   ├── tag_repository.py      # SQLite only
│   ├── tag_service.py         # single source of truth
│   └── tag_validation.py
├── ui/tags/
│   ├── tag_editor_widget.py   # Metadata tab block
│   ├── tag_chip_widget.py
│   └── tag_dialog.py          # multiline Add Tag
└── tests/
    ├── test_tag_repository.py
    ├── test_tag_service.py
    ├── test_tag_search.py
    └── test_tag_ui.py
```

---

## Database

**Path:** `%LOCALAPPDATA%/MeshStager/cache/asset_tags.sqlite` (see `USER_DATA_DIR`; legacy `%LOCALAPPDATA%/Roundup/` migrated on first launch)

```sql
CREATE TABLE asset_tags (
    id INTEGER PRIMARY KEY,
    asset_path TEXT NOT NULL,
    tag TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(asset_path, tag)
);
CREATE INDEX idx_asset_tags_path ON asset_tags(asset_path);
CREATE INDEX idx_asset_tags_tag ON asset_tags(tag);
```

- `asset_path` — normalized absolute path key  
- `tag` — normalized lowercase tag  
- UI never opens SQLite directly; use `TagService`

---

## Tag service API

```python
class TagService:
    def add_tag(asset_path, tag) -> None
    def remove_tag(asset_path, tag) -> bool
    def get_tags(asset_path) -> list[str]
    def find_assets_by_tag(tag) -> list[str]
```

Bulk add from the dialog: `add_tags_from_dialog(paths, text)`.

---

## Metadata tab UI

Under **Metadata**:

```
Tags
helmet, approved, print-ready

[helmet] [approved] [print-ready]

+ Add Tag
```

- No tags: **No tags assigned**
- **+ Add Tag** opens a simple dialog (one tag per line, Save)
- **Multi-select:** button reads **+ Add Tag to N Assets**; add only (no chip remove)
- **Single-select:** chip × removes a tag

**Bridge tags** from Blender jobs remain on the **Bridge tags** row (unchanged).

---

## Search

Use the existing search box:

| Query | Meaning |
|-------|---------|
| `tag:helmet` | Assets with user tag `helmet` |
| `tag:approved` | Assets tagged approved |
| `helmet tag:approved` | Plain term + tag filter |

---

## Success criteria (8 steps)

1. Scan folder  
2. Select STL  
3. Add tag `helmet` (+ Add Tag → dialog → Save)  
4. Close MeshStager  
5. Reopen MeshStager — tag still on asset  
6. Search `tag:helmet`  
7. Asset appears  
8. *(Optional)* Multi-select → **+ Add Tag to N Assets** applies to all  

---

## Roadmap

| Tier | Feature |
|------|---------|
| 2.1 | **Tags** (this MVP) |
| 2.2 | Favorites |
| 2.3 | Collections |
| 2.4 | Saved searches |
| 2.5 | Batch actions |

Tags are the foundation for favorites, collections, saved searches, and future batch tooling.
