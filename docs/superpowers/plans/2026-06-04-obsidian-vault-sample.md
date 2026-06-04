# Obsidian Vault Sample Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update the approved design and produce a concrete Obsidian vault sample that is human-readable first while keeping Linux.do/GitHub evidence traceability.

**Architecture:** Keep machine state in `state/knowledge/`. Reorganize the Obsidian vault into numbered human-facing folders plus `_system/` for sources and evidence. Update rules so human feedback is synced by file fingerprints and section extraction, not by full-vault agent reading.

**Tech Stack:** Markdown, Obsidian wikilinks, local filesystem operations, existing `linuxdo_surf.py` state concepts.

---

### Task 1: Update Design Spec

**Files:**
- Modify: `/Users/mortisss/Documents/linuxdo/docs/superpowers/specs/2026-06-04-linuxdo-obsidian-evidence-wiki-design.md`

- [ ] **Step 1: Replace vault tree with human-first layout**

Use this tree in the spec:

```text
LinuxDo-AI-Knowledge/
  AGENTS.md
  CLAUDE.md

  00_Home/
    index.md
    hot.md
    log.md

  10_Catalog/
    resources/
    candidates/
    comparisons/
    workflows/
    categories/
    archive/

  20_Knowledge/
    concepts/
    practices/
    claims/
    notes/
    drafts/

  30_Feedback/
    preferences/
    decisions/
    rejections/

  90_Inbox/
    review-queue/
    sessions/

  _system/
    sources/
      linuxdo/
      github/
    evidence/
      linuxdo/
      github/
```

- [ ] **Step 2: Add feedback sync design**

Add a section stating that `feedback-sync` scans file metadata and content hashes, reads only changed files, extracts frontmatter and protected human sections such as `## 我的反馈`, and writes compact summaries to machine state.

- [ ] **Step 3: Verify spec text**

Run:

```bash
rg -n "TODO|TBD|待定|不确定|placeholder|FIXME|网页|视频|web_page|comment_thread" docs/superpowers/specs/2026-06-04-linuxdo-obsidian-evidence-wiki-design.md
```

Expected: no output.

### Task 2: Reorganize Existing Vault

**Files:**
- Modify/move files under: `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge`

- [ ] **Step 1: Create target folders**

Create:

```text
00_Home/
10_Catalog/resources/
10_Catalog/candidates/
10_Catalog/comparisons/
10_Catalog/workflows/
10_Catalog/categories/
10_Catalog/archive/
20_Knowledge/concepts/
20_Knowledge/practices/
20_Knowledge/claims/
20_Knowledge/notes/
20_Knowledge/drafts/
30_Feedback/preferences/
30_Feedback/decisions/
30_Feedback/rejections/
90_Inbox/review-queue/
90_Inbox/sessions/
_system/sources/linuxdo/
_system/sources/github/
_system/evidence/linuxdo/
_system/evidence/github/
```

- [ ] **Step 2: Move existing human-facing pages**

Move existing `catalog/*` contents to `10_Catalog/*`, `wiki/*` contents to `20_Knowledge/*`, `inbox/sessions/*` to `90_Inbox/sessions/`, and root `index.md` / `log.md` to `00_Home/`.

- [ ] **Step 3: Leave no duplicate old content paths**

Remove old empty `catalog/`, `wiki/`, `inbox/`, and `raw/` directories only when they are empty.

### Task 3: Add Vault Rules and Sample Pages

**Files:**
- Modify: `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/AGENTS.md`
- Modify: `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/CLAUDE.md`
- Create/modify sample markdown files in the new vault layout.

- [ ] **Step 1: Update rule entrypoints**

`AGENTS.md` and `CLAUDE.md` must explain the new folder roles, preserve `## 我的反馈`, and state that feedback sync is incremental.

- [ ] **Step 2: Create home pages**

Create or update:

```text
00_Home/index.md
00_Home/hot.md
00_Home/log.md
```

- [ ] **Step 3: Create sample evidence/source/claim/feedback pages**

Create lightweight samples linked to the existing Superpowers pages:

```text
_system/sources/linuxdo/linuxdo-topic-2151853.md
_system/evidence/linuxdo/superpowers-token-cost-feedback.md
_system/sources/github/github-repo-obsidian-llm-wiki-local.md
_system/evidence/github/obsidian-llm-wiki-local-rejection-feedback.md
20_Knowledge/claims/superpowers-default-use-is-disputed.md
20_Knowledge/claims/obsidian-feedback-sync-should-be-incremental.md
30_Feedback/preferences/轻量工作流偏好.md
30_Feedback/decisions/Superpowers-使用决策.md
90_Inbox/review-queue/Superpowers-默认启用判断.md
```

### Task 4: Verify and Commit

**Files:**
- Repository docs under `/Users/mortisss/Documents/linuxdo`
- Vault under `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge`

- [ ] **Step 1: Verify vault structure**

Run:

```bash
find /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge -maxdepth 3 -type d -print | sort
```

Expected: includes numbered folders and `_system/`.

- [ ] **Step 2: Verify key pages**

Run:

```bash
find /Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge -maxdepth 4 -type f -name '*.md' -print | sort
```

Expected: existing Superpowers pages moved under `10_Catalog/` / `20_Knowledge/`, and sample pages exist.

- [ ] **Step 3: Commit repository docs**

Run:

```bash
git add docs/superpowers/specs/2026-06-04-linuxdo-obsidian-evidence-wiki-design.md docs/superpowers/plans/2026-06-04-obsidian-vault-sample.md
git commit -m "docs: plan obsidian vault sample"
```

Expected: commit succeeds. Vault changes are outside this git repo and are not committed here.
