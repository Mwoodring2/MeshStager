# Real user test scenarios — Roundup

## Why this doc exists

This guide is for **pre-release usability validation**: not “does the app work?” but **“do people understand what to do without being told?”**

Keep it for future versions, portfolio / case study material, and to show product thinking.

---

## What is already locked in (baseline)

- **Trust model** — no overwrite, no silent failure
- **Workflow clarity** — scan → filter → select → transfer
- **State truthfulness** — UI reflects reality
- **Guardrails** — buttons, validation, preview
- **Affordances** — tooltips, labels, hints **without** over-explaining

---

## What you are testing (not “success”)

When you run sessions, you are watching for:

- **Hesitation** — long pauses, mouse wandering, re-reading
- **Confusion** — wrong clicks, backtracking, verbal “wait, what?”
- **Incorrect assumptions** — mental model that does not match the app
- **Invisible expectations** — things users believe are true but the app never stated

---

## Friction points to watch (by area)

### 1. “Why do I need to scan?”

Users may expect files to already be there or not understand **working set**.

**Watch:**

- How long before they click **Scan Source**
- Whether they look stuck or confused before doing it

### 2. Filters vs search (layered mental model)

Users may treat filters like a **global search** or not realize filters are **layered**.

**Watch:**

- Do they try typing **before** scanning?
- When results change or disappear, do they understand **why**?

### 3. Destination + summary panel awareness

Many users **focus on the table** and **ignore the right panel**.

**Watch:**

- Do they notice the summary / destination context?
- Do they **trust** it before clicking **Move**?

### 4. Preview dialog comprehension

Preview may say something like: only OK rows run; blocked/error skipped; no overwrite.

Users may still skim or not fully understand **“blocked.”**

**Watch:**

- Do they **pause** on the preview?
- Do they **read** it or dismiss immediately?

### 5. Copy vs move

Even experienced users sometimes mix these up.

**Watch:**

- Do they expect **copy** to remove files from the source?
- After execution, do they **notice** the difference (source vs destination behavior)?

---

## What **not** to do during testing

Resist:

- Explaining the UI unprompted
- Clarifying terms mid-task
- Guiding them to the “right” button

**Let them struggle a little** — that hesitation *is* the data.

---

## After testing: how we respond

When you return with **“here’s where people got stuck,”** the goal is **not** a full redesign.

Typical adjustments:

- Wording (labels, preview text, empty states)
- Layout emphasis (what draws the eye first)
- Control order (if flow is wrong)
- **One** small affordance at a time — keep the product clean

---

## Where you are & next milestone

- **Now:** pre-release usability validation (a rare stage to reach properly)
- **Next:** release build + shareable EXE — when the product becomes **concretely** shippable

---

## Session log (optional)

Use this table during or after each session.

| Date | Participant (anon) | Task / scenario | Stuck where? | Assumption wrong? | Quote / note |
|------|---------------------|-----------------|--------------|-------------------|--------------|
|      |                     |                 |              |                   |              |
