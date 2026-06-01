---
name: linuxdo-surfing
description: Use when Codex should surf Linux.do with logged-in browser state, discover AI tools, skills, plugins, workflows, community feedback, GitHub leads, or run a sustained Linux.do research loop that writes durable knowledge state and Obsidian notes.
---

# Linux.do Surfing

## What This Skill Is

This skill guides Codex while reading Linux.do for AI coding workflows, skills, plugins, agents, MCP servers, tools, 中转站, and practical experience. The local CLI `tools/linuxdo_surf.py` is the deterministic state helper; browser reading still happens through Codex Browser or the user's Chrome login state.

The first-class workflow is now:

- machine state in `state/knowledge/`;
- human-facing knowledge in an Obsidian vault;
- lightweight indexes instead of loading old `readings_all.json`;
- batch reading, batch writing, and feedback before the next run.

Do not treat Linux.do as a source of settled truth. Forum content can be wrong, outdated, edited, or contradicted by later replies. Save evidence, uncertainty, disputes, and follow-up needs.

## Before A Surfing Run

1. Load the user's config, usually `config/knowledge_sources.json`.
2. Sync human feedback from Obsidian before generating a new task:

```bash
python3 tools/linuxdo_surf.py feedback-sync --config config/knowledge_sources.json
```

3. Sync LinuxDo Scripts bookmark export if the local JSON exists:

```bash
python3 tools/linuxdo_surf.py bookmark-sync --config config/knowledge_sources.json
```

4. Generate a knowledge task:

```bash
python3 tools/linuxdo_surf.py knowledge-plan --config config/knowledge_sources.json --batch-size 20
```

If no Obsidian vault exists yet, create or ask for `obsidian_vault_path` first, then run:

```bash
python3 tools/linuxdo_surf.py knowledge-init --config config/knowledge_sources.json
```

## Reading Policy

Use DOM/JSON/text extraction first. Render only when needed for visual evidence, status evidence, layout semantics, screenshots, videos, UI/WebUI/TUI, install/config steps, error screenshots, or missing key content. After rendering, extract only the necessary information; do not keep screenshots in context longer than needed.

Follow the task's reading levels:

- Level 0: metadata only or skip.
- Level 1: main post + a few high-signal replies + minimal context.
- Level 2: main post + popular, disputed, linked, author, and contextual replies.
- Level 3: deep read most replies for disputes, comparisons, and real-world testing threads.

For active old topics, do not read only the newest reply. Capture original context, historical corrections, and recent updates separately.

Use `references/linuxdo-reading-playbook.md` when deciding how to read an individual topic.
Use `references/reading-schema.md` when shaping a structured reading record.

## What To Extract

Save only information that can drive future action:

- valuable Linux.do topic links;
- tools, skills, plugins, MCP servers, CLIs, workflows, 中转站, or agents;
- high-signal authors;
- positive feedback, negative feedback, risks, corrections, and comparisons;
- GitHub repos or search leads worth verifying;
- unresolved disputes or evidence that needs later update.

Do not save generic praise, shallow summaries, every URL, or noisy replies that do not change a decision.

## Batch Write

After each batch, write structured readings back to state and Obsidian:

```bash
python3 tools/linuxdo_surf.py knowledge-session \
  --config config/knowledge_sources.json \
  --task output/linuxdo_surf/knowledge_task_latest.json \
  --readings output/linuxdo_surf/knowledge_readings.json \
  --batch-id 001
```

Skipped and metadata-only items still matter: they update skip counters so repeated low-value items can be deprioritized later.

Every 5-10 batches, or when repeated skips accumulate, run:

```bash
python3 tools/linuxdo_surf.py knowledge-maintain --config config/knowledge_sources.json
```

## Continuous Goal Behavior

For `/goal` or sustained surfing:

1. Run feedback and bookmark sync before the first task.
2. Read the next batch from `knowledge-plan`.
3. Extend through only relevant leads: better evidence, alternatives, strong positive/negative feedback, GitHub repos, author trails, or unresolved disputes.
4. Save every batch with `knowledge-session`.
5. Keep chat checkpoints compact; detailed evidence belongs in state files and Obsidian.

Use `references/continuous-loop.md` for loop tactics.
Use `references/github-research.md` when Linux.do leads need GitHub validation.

## Output Style

Chat output should help the user decide, not replay the whole forum:

- 3-5 top findings;
- priority buckets: `马上试`, `收藏观察`, `暂时跳过`;
- every post read in a compact index;
- key evidence and confidence for valuable items;
- next leads worth following;
- saved artifact paths.

For Obsidian pages, preserve `## 我的反馈`. Human feedback can be messy or provisional; sync it, consider it, but do not blindly treat it as ground truth.
