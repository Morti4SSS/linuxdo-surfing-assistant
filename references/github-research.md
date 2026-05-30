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

## Loop

1. Run `scripts/linuxdo_surf.py github-plan` to create a GitHub task from frontier queues.
2. Inspect concrete repos with GitHub MCP or official GitHub pages.
3. Search GitHub for queued tool, skill, plugin, MCP, CLI, and workflow terms.
4. Record findings as `github_readings`.
5. Run `scripts/linuxdo_surf.py github-result` to update reviewed state and merge related repos/tools back into the frontier.
6. Continue only if new leads are relevant to the current target.

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
