# User tags (Tier 2.1)

User tags are your own labels for assets in the current scan. They help you organize work **without renaming, moving, or changing** files on disk.

Examples: `vehicle`, `head`, `armor`, `print-ready`, `customer-approved`, `needs-review`, `mvp`.

---

## What tags are not

- Tags do **not** rename files.
- Tags do **not** move or copy files.
- Tags do **not** modify mesh data, thumbnails, or scan results.
- Tags are **not** Blender bridge metadata (those appear under **Bridge tags** on the Metadata tab).

---

## Where tags are stored

Tags are saved in a local SQLite database on your PC:

`%LOCALAPPDATA%\MeshStager\cache\asset_tags.sqlite`

Tags persist when you close and reopen MeshStager. They are keyed by the **full path** of each file, so the same file keeps its tags across sessions.

Legacy Roundup data under `%LOCALAPPDATA%\Roundup\` is migrated on first launch.

---

## How to add tags

1. **Scan** a source folder.
2. **Select** one or more assets in the table or gallery.
3. Open the **Metadata** tab in the Asset inspector.
4. Under **Tags**, click **+ Add Tag** (or **+ Add Tag to N Assets** when several rows are selected).
5. In the dialog, enter one tag per line (commas also work), for example:

   ```
   helmet
   approved
   print-ready
   ```

6. Click **Save**.

Tags appear as a comma list and as chips under the summary line.

---

## How to remove tags

- **Single selection:** click **×** on a tag chip in the Metadata tab.
- **Multi-select:** removal from chips is not shown in MVP; clear tags per file by selecting one asset at a time, or add only via the bulk dialog.

---

## Multi-select tagging

When multiple assets are selected:

- The button reads **+ Add Tag to N Assets** (N = selection count).
- Every tag you save in the dialog is applied to **each** selected file.
- The tag list shows the **union** of tags on any selected file (tags that appear on at least one selection).

---

## How to search with `tag:name`

Use the main **Search** box (same field as name and `ext:` filters).

| Search | Finds |
|--------|--------|
| `tag:print-ready` | Assets you tagged `print-ready` |
| `tag:armor` | Assets tagged `armor` |
| `tag:customer-approved` | Assets tagged `customer-approved` |
| `helmet tag:approved` | Name/path contains “helmet” **and** tag `approved` |

Tag names are normalized to lowercase in storage (`Print-Ready` → `print-ready`).

---

## Examples

```
tag:print-ready
tag:armor
tag:customer-approved
tag:needs-review
tag:mvp
```

Combine with other tokens:

```
ext:stl tag:print-ready
folder:vehicles tag:approved
```

---

## Related docs

- Developer / schema notes: [`TIER2_TAGS_MVP.md`](TIER2_TAGS_MVP.md)
- Core freeze (unchanged by tags): [`PRIME_V1_CORE_FREEZE.md`](PRIME_V1_CORE_FREEZE.md)
