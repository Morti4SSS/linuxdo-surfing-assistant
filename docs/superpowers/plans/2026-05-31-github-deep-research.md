# GitHub Deep Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a tested GitHub verification and discovery layer to `linuxdo-surfing`.

**Architecture:** Keep Linux.do browser reading as the main workflow. Add GitHub discovery queues to the existing frontier state helper, plus `github-plan` and `github-result` commands that prepare and preserve GitHub MCP research work.

**Tech Stack:** Python standard library, `unittest`, JSON state files, Codex skill markdown references, GitHub MCP/manual GitHub page inspection at runtime.

---

### Task 1: Discovery Model

**Files:**
- Modify: `tools/linuxdo_surf.py`
- Test: `tests/test_linuxdo_surf.py`

- [x] Write failing tests for `github-repo-research`, `github-search`, and reviewed GitHub state.
- [x] Add discovery queue names and normalized state fields.
- [x] Extract GitHub repos from Linux.do summaries, follow-up links, and high-value replies.
- [x] Convert tool names into GitHub search leads.
- [x] Run targeted tests and verify they pass.

### Task 2: GitHub Task Package

**Files:**
- Modify: `tools/linuxdo_surf.py`
- Test: `tests/test_linuxdo_surf.py`

- [x] Write failing tests for `github-plan`.
- [x] Select unreviewed repos and searches from frontier queues.
- [x] Generate `github_task_<mode>.json` with GitHub MCP instructions and budgets.
- [x] Run targeted tests and verify they pass.

### Task 3: GitHub Result Merge

**Files:**
- Modify: `tools/linuxdo_surf.py`
- Test: `tests/test_linuxdo_surf.py`

- [x] Write failing tests for `github-result`.
- [x] Save GitHub reading result JSON.
- [x] Update reviewed repo/search state.
- [x] Merge related repos and tools back into GitHub discovery queues.
- [x] Run full tests and verify they pass.

### Task 4: Skill Documentation

**Files:**
- Modify: `SKILL.md`
- Modify: `references/continuous-loop.md`
- Modify: `references/reading-schema.md`
- Modify: `references/skill-evidence.md`
- Create: `references/github-research.md`
- Test: `tests/test_skill_package.py`

- [x] Document GitHub as an evidence and extension source.
- [x] Document `github-plan` and `github-result`.
- [x] Add package tests proving the skill references GitHub research rules.
- [x] Run full tests and verify they pass.

### Task 5: Release and Convergence

**Files:**
- Modify as needed from review findings.

- [x] Sync the installed global skill directory.
- [x] Commit and push a functional checkpoint.
- [ ] Run five consecutive verification/check rounds.
- [x] Fix any actionable issue found during those rounds.
- [ ] Commit and push the final version.
