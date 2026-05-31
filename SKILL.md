---
name: linuxdo-surfing
description: Use when the user wants Codex to surf Linux.do with logged-in browser state, read posts, discover AI tools, skills, plugins, workflows, community feedback, or run a /goal-style continuous Linux.do research loop that iterates through valuable links and discussion leads.
---

# Linux.do Surfing

## What This Skill Is

This is a Codex Linux.do surfing skill. The skill is the product: it uses Codex 内置浏览器, the user's saved Linux.do login state, JSON-first structured reading, and render-on-demand checks to read posts, judge value, follow leads, and preserve evidence. The local `scripts/linuxdo_surf.py` entrypoint delegates to `tools/linuxdo_surf.py`; that helper is a 状态脚本 for queues, sessions, and evidence packages. It is useful, but it is not the main surf assistant and 不是主体.

Use this skill when the user asks to:

- surf Linux.do, 淘金, 找帖子, 查 AI 工具, 查 skill 评价, 找工作流, 查 GitHub 项目, or avoid falling behind;
- research a topic from Linux.do posts;
- inspect posts the user already opened in Chrome;
- continue a previous Linux.do surfing session;
- verify Linux.do-discovered projects, skills, plugins, tools, workflows, or repos on GitHub;
- search GitHub for useful AI coding, workflow, skill, plugin, MCP, or CLI projects using the same frontier-loop mindset;
- run `/goal` or long-running continuous surfing until a target or stop condition is met.

Do not use this skill for generic web research outside Linux.do unless Linux.do discussion or GitHub project evidence is the evidence source.

## Core Rule

Reading is **JSON-first + 按需渲染核验**. Linux.do requires login state, so use Codex 内置浏览器 for Codex-led discovery and authenticated `/t/{id}.json` access. JSON is a fast structured reading channel for title, body, replies, authors, links, and floor structure; JSON 不能替代原帖渲染核验. 每帖 JSON 深读后必须判断 `render_required`. If the user says they already selected posts in Chrome or tab groups, treat Chrome as a user-curated reading source. Do not pretend the state script can read protected posts by itself.

Set `render_required=true` and open the original rendered post when the JSON pass sees screenshots, images, videos, UI/WebUI/TUI, frontend/aesthetic/card/dashboard/status-bar/workflow-diagram claims, tutorial/install/config/build/PowerShell/error-screenshot content, document layout outputs, low/medium confidence `马上试` items, or visual references such as "如图", "看图", "上图", "下图", "截图里", or "效果如下". Skip render only for low-value pure Q&A, pure complaints, pure resource entrances, pure model scores, or cases where JSON fully supports the conclusion and there is no visual/operation/interface judgment.

## Workflow

1. Classify the request into one mode: topic research, goldmine, skill feedback, or skill/workflow discovery. See `references/surfing-modes.md` when the mode or output shape is unclear.
2. If starting or resuming a long task, generate or load a frontier queue with `scripts/linuxdo_surf.py goal-plan`. It delegates to `tools/linuxdo_surf.py`; use both only as state helpers.
3. Open Linux.do with Codex 内置浏览器 and read the selected posts through authenticated JSON first when possible. For active-old posts, read the first post, key historical replies, recent replies, and high-value replies. Do not only read the newest reply.
4. For every post, decide `render_required`; if required and budget allows, open the rendered page/images during the same batch and set `render_checked` / `image_checked`.
5. Record each reading using the schema in `references/reading-schema.md`.
6. Extract leads from the post and replies: authors, Linux.do links, mentioned tools, skill names, plugins, GitHub repos, workflows, risks, and comparisons.
7. For `/goal` or this skill's continuous mode, 持续迭代: after every batch, use valuable leads from the current posts to 延展冲浪 into the next batch when they match the user's target. Continue until the budget or stop condition is reached.
8. Save the batch with `scripts/linuxdo_surf.py session` so read state and discovery queues are preserved.
9. Choose a lightweight platform strategy instead of a heavy parallel hybrid:
   - `linuxdo-only`: only read Linux.do; save GitHub-looking leads for later.
   - `github-only`: search or inspect GitHub directly; do not require Linux.do first.
   - `linuxdo-first`: read Linux.do first, then use GitHub only to verify or extend worthwhile project/tool leads.
   - `github-first`: inspect GitHub first, then use Linux.do only to backfill community feedback.
10. When repos, projects, skills, plugins, tools, or workflows need validation, generate a GitHub task with `scripts/linuxdo_surf.py github-plan`, inspect with GitHub MCP or official GitHub pages, then save findings with `scripts/linuxdo_surf.py github-result`. See `references/github-research.md`.
11. If an older single-platform session/result needs the other platform, use `scripts/linuxdo_surf.py backfill-plan` to create a compact auxiliary task from the saved evidence.
12. If a saved session has old JSON-only records, missed checks, or too many `render_required` candidates for the batch budget, use `scripts/linuxdo_surf.py visual-review-plan` as a targeted补核验 tool. It keeps legacy `visual_evidence_needed` compatibility, but it is not the default reading path.
13. If the output should feed the skill-management project, create a skill evidence package. See `references/skill-evidence.md`.

For self-selected posts or lightweight goldmine searches, read only the requested number of posts and stop with a compact result. Do not invent a next-batch loop unless the user invokes `/goal`, asks to continue until a target, or explicitly requests sustained surfing.

## Continuous `/goal` Behavior

When invoked through `/goal` or asked to keep surfing, do not treat the task as a single summary pass. Run a loop:

- choose the next batch from the frontier;
- read posts through authenticated JSON first, then open rendered pages/images for `render_required` items;
- identify new valuable leads inside posts and comments;
- extend the search through those leads when relevant;
- verify concrete repos or search GitHub when Linux.do mentions projects, skills, plugins, MCP servers, CLIs, or workflows worth deeper evidence;
- save a session;
- continue from the updated frontier until a stop condition is met.

Default stop conditions: read budget reached, time budget reached, next batch is empty, high-value discoveries dry up across consecutive batches, or the user-provided target is satisfied. Detailed loop guidance is in `references/continuous-loop.md`.

If a batch has no meaningful harvest, adjust before stopping: 切换热度排序, 切换最新排序, search 同义词, and inspect whether previous posts contain leads worth deeper search. Use `references/linuxdo-reading-playbook.md` for Linux.do-specific reading and adjustment tactics.

## State Helper

Use `scripts/linuxdo_surf.py` for deterministic state work. It delegates to `tools/linuxdo_surf.py`.

```powershell
python scripts/linuxdo_surf.py goal-plan --mode goldmine --queue state/linuxdo_frontier_queue.json --state state/linuxdo_surf_state.json
python scripts/linuxdo_surf.py session --task output/linuxdo_surf/goal_task_goldmine.json --readings output/linuxdo_surf/readings.json --stop-reason "达到本轮深读预算"
python scripts/linuxdo_surf.py github-plan --mode discover --strategy linuxdo-first --queue state/linuxdo_frontier_queue.json --state state/linuxdo_surf_state.json
python scripts/linuxdo_surf.py github-result --task output/linuxdo_surf/github_task_discover.json --readings output/linuxdo_surf/github_readings.json
python scripts/linuxdo_surf.py github-plan --mode discover --strategy github-only --query "codex workflow skill"
python scripts/linuxdo_surf.py backfill-plan --source-platform linuxdo --mode discover --input output/linuxdo_surf/mode_result_discover.json
python scripts/linuxdo_surf.py backfill-plan --source-platform github --mode discover --input output/linuxdo_surf/github_result_discover.json --topics output/linuxdo_skill_research/topic_details_top220.json
python scripts/linuxdo_surf.py visual-review-plan --input output/linuxdo_surf/mode_result_discover.json --state state/linuxdo_surf_state.json
python scripts/linuxdo_surf.py evidence --skills skill-creator --readings output/linuxdo_surf/readings.json
```

The script does not replace reading or GitHub inspection. It only ranks candidates, stores sessions, merges discovery queues, generates GitHub/backfill task packages, and prevents duplicate work.

## Output Style

Default to an absorption-friendly output. The chat response is for decisions; session and evidence files are for traceability. Do not dump full reading notes, long reply lists, or tens of thousands of words into chat unless the user explicitly asks for a full export.

Use this two-layer default shape:

- one-screen brief: 3-5 top findings, each with one sentence explaining why it matters;
- priority buckets: `马上试`, `收藏观察`, `暂时跳过`;
- read-post index: include every post read in the pass, with title, link, 发现状态, value tag, one-line summary, and whether it is expandable;
- evidence index: for valuable posts, include key reply point and confidence instead of full post narration;
- next leads worth following, only when they are clearly connected to the user's goal;
- saved artifacts: mention session or evidence package paths when they were created.

The 3-5 limit applies only to the top-findings brief, not to the read-post index. If a pass reads many posts, list every post read so the user can see what was covered and where value was or was not found.

For `/goal` or sustained surfing, report compact checkpoints after each batch and keep detailed reading records in files. The final answer should be a decision brief plus a complete read-post index, not a transcript. If the user wants more, invite expansion by item number, for example "展开第 2 个工具的优劣".

Avoid fixed daily reports unless the user explicitly asks for one.
