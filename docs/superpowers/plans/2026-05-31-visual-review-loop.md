# Visual Review Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a lightweight visual/render review loop so Linux.do JSON readings do not silently miss UI, screenshot, video, tutorial, workflow diagram, WebUI, or aesthetic evidence.

**Architecture:** Keep JSON deep reading as the default. Add structured visual fields to readings/results, a deterministic `visual-review-plan` command that selects only posts needing render回看, and docs that tell Codex when to use browser rendering. The state helper generates review tasks; it does not inspect protected pages by itself.

**Tech Stack:** Python standard library state helper, unittest tests, Markdown skill references.

---

### Task 1: Preserve Visual Review Fields

**Files:**
- Modify: `tools/linuxdo_surf.py`
- Test: `tests/test_linuxdo_surf.py`

- [ ] **Step 1: Write failing test**

Add a test that `build_mode_result` preserves these reading fields:

```python
"visual_evidence_needed": True,
"visual_reason": "UI 截图决定结论",
"visual_review_status": "needed",
"visual_review_notes": [],
"visual_assets": ["screenshot: status bar"],
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
python -m unittest tests.test_linuxdo_surf.LinuxdoSurfTests.test_build_mode_result_preserves_visual_review_fields
```

Expected: FAIL because fields are missing.

- [ ] **Step 3: Implement minimal field preservation**

Add those fields in `build_mode_result` items, defaulting to:

```python
"visual_evidence_needed": bool(reading.get("visual_evidence_needed", False)),
"visual_reason": reading.get("visual_reason", ""),
"visual_review_status": reading.get("visual_review_status", "not-needed"),
"visual_review_notes": reading.get("visual_review_notes", []),
"visual_assets": reading.get("visual_assets", []),
```

- [ ] **Step 4: Run test and full suite**

Run:

```powershell
python -m unittest tests.test_linuxdo_surf.LinuxdoSurfTests.test_build_mode_result_preserves_visual_review_fields
python -m unittest discover -s tests
```

Expected: both pass.

### Task 2: Generate Visual Review Tasks

**Files:**
- Modify: `tools/linuxdo_surf.py`
- Test: `tests/test_linuxdo_surf.py`

- [ ] **Step 1: Write failing CLI test**

Add `test_cli_visual_review_plan_selects_only_needed_unchecked_items`.

Input `mode_result_discover.json` with three `items`:

```json
[
  {"id": 1, "title": "UI 工具", "url": "https://linux.do/t/topic/1", "summary": "截图展示状态栏", "visual_evidence_needed": true, "visual_reason": "UI 截图", "visual_review_status": "needed"},
  {"id": 2, "title": "纯讨论", "url": "https://linux.do/t/topic/2", "summary": "纯文字讨论"},
  {"id": 3, "title": "已回看", "url": "https://linux.do/t/topic/3", "summary": "教程截图", "visual_evidence_needed": true, "visual_review_status": "checked"}
]
```

Run:

```python
linuxdo_surf.main([
  "visual-review-plan",
  "--input", str(result_path),
  "--output", str(out_dir),
  "--max-topics", "5",
])
```

Assert `visual_review_task.json` includes only item 1 and instructions mention Codex browser/rendered page.

- [ ] **Step 2: Run test to verify failure**

Run the single new test. Expected: argparse rejects unknown command.

- [ ] **Step 3: Implement command**

Add:

```python
def build_visual_review_task(readings, max_topics):
    ...
```

Select items where `visual_evidence_needed` is true and `visual_review_status` is not `checked`.

Add parser command:

```powershell
visual-review-plan --input <path> --output output/linuxdo_surf --max-topics 10
```

Write `visual_review_task.json`.

- [ ] **Step 4: Run tests**

Run the new test and full suite.

### Task 3: Document Visual Review Discipline

**Files:**
- Modify: `SKILL.md`
- Modify: `references/reading-schema.md`
- Modify: `references/continuous-loop.md`
- Modify: `references/linuxdo-reading-playbook.md`
- Test: `tests/test_skill_package.py`

- [ ] **Step 1: Write failing package test**

Assert docs mention:

- `visual_evidence_needed`
- `visual-review-plan`
- `rendered page`
- `不能把 JSON 记录默认等同于已完成渲染核验`

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
python -m unittest tests.test_skill_package.LinuxdoSurfingSkillPackageTests
```

- [ ] **Step 3: Update docs**

Document:

- JSON reading is enough for pure text discussions.
- Visual review is needed for screenshots, video, UI/WebUI/TUI, tutorial steps, install/config screens, workflow diagrams, cards, layout, and aesthetic claims.
- Do not review every post; use a budgeted queue.
- Save visual findings back as `visual_review_status`, `visual_review_notes`, and `visual_assets`.

- [ ] **Step 4: Run package test and full suite**

Run:

```powershell
python -m unittest discover -s tests
```

### Task 4: Sync, Verify, Commit, Push

**Files:**
- Sync to: `C:\Users\hp\.codex\skills\linuxdo-surfing`

- [ ] **Step 1: Sync global skill files**

Copy updated `SKILL.md`, `tools/linuxdo_surf.py`, and changed references.

- [ ] **Step 2: Verify local and global commands**

Run:

```powershell
python scripts\linuxdo_surf.py visual-review-plan --help
python C:\Users\hp\.codex\skills\linuxdo-surfing\scripts\linuxdo_surf.py visual-review-plan --help
python -m unittest discover -s tests
git diff --check
```

- [ ] **Step 3: Commit and push**

Run:

```powershell
git add SKILL.md references\reading-schema.md references\continuous-loop.md references\linuxdo-reading-playbook.md tools\linuxdo_surf.py tests\test_linuxdo_surf.py tests\test_skill_package.py docs\superpowers\plans\2026-05-31-visual-review-loop.md
git commit -m "feat: add visual review loop for linuxdo readings"
git push origin master
```
