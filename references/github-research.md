# GitHub Research

Use this reference when Linux.do surfing discovers GitHub projects, skills, plugins, tools, workflows, MCP servers, CLIs, or when the user asks to search GitHub directly for useful AI workflow material.

## Role

GitHub is an evidence and extension source. It does not replace Linux.do community reading. Use it to answer:

- Is the project alive?
- Is the README clear enough to try?
- Are issues and PRs healthy or alarming?
- Are releases/recent commits current?
- Does it overlap with existing skills, plugins, or workflows?
- Are there better alternatives linked from README, issues, topics, examples, or related repos?

## Strategy Modes

Use one of four lightweight strategies. Do not default to a heavy `hybrid` flow with two agents exchanging findings.

- `linuxdo-only`: stay on Linux.do and record GitHub-looking leads for later.
- `github-only`: search GitHub directly from the user's query or inspect known repos; no Linux.do pass is required.
- `linuxdo-first`: read Linux.do first, then send only worthwhile projects, skills, plugins, tools, workflows, and repos to GitHub.
- `github-first`: inspect GitHub first, then use Linux.do only to backfill community feedback or adoption signals.

## Loop

1. Run `scripts/linuxdo_surf.py github-plan` to create a GitHub task from frontier queues.
2. Inspect concrete repos with GitHub MCP or official GitHub pages.
3. Search GitHub for queued tool, skill, plugin, MCP, CLI, and workflow terms.
4. Record findings as `github_readings`.
5. Run `scripts/linuxdo_surf.py github-result` to update reviewed state and merge related repos/tools back into the frontier.
6. Continue only if new leads are relevant to the current target.

For direct GitHub research, run:

```powershell
python scripts/linuxdo_surf.py github-plan --mode discover --strategy github-only --query "codex workflow skill"
```

## Backfill

Use `backfill-plan` when a previous single-platform result already exists and only the auxiliary platform is missing.

- Linux.do result/session to GitHub: extracts repos and tool names from `items`, `readings`, or `github_repos`, merges them into the frontier, then writes `github_task_<mode>.json`.
- GitHub result to Linux.do: extracts repo names, source queries, and related tools, optionally ranks `--topics`, then writes `browser_task_<mode>.json` with strategy `github-first`. If no topic cache is available, use the generated query to search Linux.do in the browser.

```powershell
python scripts/linuxdo_surf.py backfill-plan --source-platform linuxdo --mode discover --input output/linuxdo_surf/mode_result_discover.json
python scripts/linuxdo_surf.py backfill-plan --source-platform github --mode discover --input output/linuxdo_surf/github_result_discover.json --topics output/linuxdo_skill_research/topic_details_top220.json
```

Backfill is a targeted补深挖 step, not a new long-running hybrid loop.

## GitHub Reading Shape

```json
{
  "repo": "owner/name",
  "url": "https://github.com/owner/name",
  "summary": "一句到一段核心判断",
  "stars": 0,
  "last_commit_at": "2026-05-31T00:00:00Z",
  "positive_signals": [],
  "negative_signals": [],
  "risk_notes": [],
  "related_repos": [],
  "related_tools": [],
  "recommendation": "马上试|收藏观察|暂时跳过",
  "confidence": "high|medium|low"
}
```

## Selection Heuristics

Do not sort only by stars. Prefer repos that are recently active, have a clear README, solve a real workflow bottleneck, are mentioned by Linux.do users, or are linked by a trusted repo. Keep low-star but high-fit projects in the index when they look practical.

## Output

User-facing output should mirror Linux.do compression:

- top GitHub findings;
- repo index with links, value tag, one-line summary, and confidence;
- recommendation bucket: `马上试`, `收藏观察`, `暂时跳过`;
- related repos/tools that justify another batch.
