---
name: linuxdo-surfing
description: Use when the user wants Codex to surf Linux.do with logged-in browser state, read posts, discover AI tools, skills, plugins, workflows, community feedback, or run a /goal-style continuous Linux.do research loop that iterates through valuable links and discussion leads.
---

# Linux.do Surfing

## What This Skill Is

This is a Codex browser-reading skill for Linux.do. The skill is the product: it uses Codex 内置浏览器 and the user's saved Linux.do login state to read posts, judge value, follow leads, and preserve evidence. The local `scripts/linuxdo_surf.py` entrypoint delegates to `tools/linuxdo_surf.py`; that helper is a 状态脚本 for queues, sessions, and evidence packages. It is useful, but it is not the main surf assistant and 不是主体.

Use this skill when the user asks to:

- surf Linux.do, 淘金, 找帖子, 查 AI 工具, 查 skill 评价, 找工作流, or avoid falling behind;
- research a topic from Linux.do posts;
- inspect posts the user already opened in Chrome;
- continue a previous Linux.do surfing session;
- run `/goal` or long-running continuous surfing until a target or stop condition is met.

Do not use this skill for generic web research outside Linux.do unless Linux.do discussion is the evidence source.

## Core Rule

Reading is browser-first. Linux.do requires login state, so use Codex 内置浏览器 for Codex-led discovery. If the user says they already selected posts in Chrome or tab groups, treat Chrome as a user-curated reading source. Do not pretend the state script can read protected posts by itself.

## Workflow

1. Classify the request into one mode: topic research, goldmine, skill feedback, or skill/workflow discovery. See `references/surfing-modes.md` when the mode or output shape is unclear.
2. If starting or resuming a long task, generate or load a frontier queue with `scripts/linuxdo_surf.py goal-plan`. It delegates to `tools/linuxdo_surf.py`; use both only as state helpers.
3. Open Linux.do with Codex 内置浏览器 and read the selected posts. For active-old posts, read the first post, key historical replies, recent replies, and high-value replies. Do not only read the newest reply.
4. Record each reading using the schema in `references/reading-schema.md`.
5. Extract leads from the post and replies: authors, Linux.do links, mentioned tools, skill names, plugins, GitHub repos, workflows, risks, and comparisons.
6. For `/goal` or this skill's continuous mode, 持续迭代: after every batch, use valuable leads from the current posts to 延展冲浪 into the next batch when they match the user's target. Continue until the budget or stop condition is reached.
7. Save the batch with `scripts/linuxdo_surf.py session` so read state and discovery queues are preserved.
8. If the output should feed the skill-management project, create a skill evidence package. See `references/skill-evidence.md`.

## Continuous `/goal` Behavior

When invoked through `/goal` or asked to keep surfing, do not treat the task as a single summary pass. Run a loop:

- choose the next batch from the frontier;
- read posts deeply with the browser;
- identify new valuable leads inside posts and comments;
- extend the search through those leads when relevant;
- save a session;
- continue from the updated frontier until a stop condition is met.

Default stop conditions: read budget reached, time budget reached, next batch is empty, high-value discoveries dry up across consecutive batches, or the user-provided target is satisfied. Detailed loop guidance is in `references/continuous-loop.md`.

## State Helper

Use `scripts/linuxdo_surf.py` for deterministic state work. It delegates to `tools/linuxdo_surf.py`.

```powershell
python scripts/linuxdo_surf.py goal-plan --mode goldmine --queue state/linuxdo_frontier_queue.json --state state/linuxdo_surf_state.json
python scripts/linuxdo_surf.py session --task output/linuxdo_surf/goal_task_goldmine.json --readings output/linuxdo_surf/readings.json --stop-reason "达到本轮深读预算"
python scripts/linuxdo_surf.py evidence --skills skill-creator --readings output/linuxdo_surf/readings.json
```

The script does not replace reading. It only ranks candidates, stores sessions, merges discovery queues, and prevents duplicate work.

## Output Style

Prefer structured, high-signal output:

- what was read;
- what is genuinely valuable;
- tool/skill/workflow names with evidence;
- positive and negative community feedback;
- next leads worth following;
- what was saved to session or evidence packages.

Avoid fixed daily reports unless the user explicitly asks for one.
