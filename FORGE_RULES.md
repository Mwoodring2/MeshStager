# FORGE_RULES.md

Working rules for any AI assistant picking up **MeshStager**. Read this first, then
[`docs/AI_PROJECT_HANDOFF.md`](docs/AI_PROJECT_HANDOFF.md) for project state.

## MeshStager working rules

1. **Open implementation guidance with "Best Cursor prompt to apply this patch".** When you propose
   a change, lead with a copy-pasteable prompt that applies it, then explain the reasoning.
2. **Prefer small, testable patches.** One concern per change, with the test that proves it. Split
   large work into reviewable steps instead of one sweeping edit.
3. **Preserve current behavior unless fixing a confirmed bug.** Confirm the bug first — reproduce it
   or point at failing evidence. Refactors, renames, and "while I was in there" cleanups are not
   free; they are regressions waiting to happen.
4. **No `assert` statements.** They disappear under optimization and are not a safety mechanism.
5. **Use explicit runtime checks and logging.** Validate inputs, fail with clear messages, and log
   through the `logging` module rather than printing or silently swallowing errors.
6. **Keep the source repo clean; release artifacts stay ignored.** No ZIPs, EXEs, installers,
   `dist/`, `build/`, `release/`, caches, databases, or private meshes. See `.gitignore`.
7. **Windows-first, PySide6-first.** Windows 10/11 is the supported target and PySide6 is the UI
   toolkit. Do not add a second GUI framework or a cross-platform abstraction layer for its own
   sake.

## Also non-negotiable

- Thumbnails exist so a user can identify an asset; speed work must never drop below that bar.
- Every modal follows `docs/YARD_RESPONSIVE_DIALOG_STANDARD.md` (resizable, scrolled body, action
  buttons pinned outside the scroll area, centered and clamped to the screen).
- Typing required, ~100-character lines, docstrings on public functions and classes.
- Do not commit automatically. Show the change, let the user decide.
