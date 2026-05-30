# GitHub Deep Research Design

## Goal

Extend `linuxdo-surfing` so GitHub can verify and extend Linux.do discoveries. Linux.do remains the primary community-reading source. GitHub becomes a second evidence source for projects, skills, plugins, tools, workflows, and repos discovered during surfing, and it can also be searched directly with the same frontier-loop mindset.

## Scope

In scope:

- Extract GitHub repositories from Linux.do readings, follow-up links, and high-value replies.
- Convert tool, skill, plugin, and workflow names into GitHub search leads.
- Generate a GitHub research task package from the existing frontier queue.
- Save GitHub research results, update reviewed repo/search state, and merge related repos/tools back into discovery queues.
- Document how Codex should use GitHub MCP or official GitHub pages for repo inspection.

Out of scope:

- Automatic installation, enabling, disabling, or rewriting of skills and plugins.
- Replacing Linux.do browser reading with GitHub-only research.
- Full GitHub crawling or unauthenticated scraping.

## Data Model

The frontier `discovery_queues` gains:

- `github-repo-research`: concrete repos such as `openai/codex`, with source Linux.do topic links, source GitHub repos, focus, score, and depth.
- `github-search`: search queries derived from tools, skills, plugins, MCP names, and workflow names.

State gains:

- `reviewed_github_repos`
- `reviewed_github_searches`

GitHub readings should preserve repo URL, summary, positive and negative signals, risk notes, related repos, related tools, recommendation, and confidence.

## Workflow

1. Read Linux.do posts with Codex browser.
2. Save session with `scripts/linuxdo_surf.py session`.
3. Extract Linux.do and GitHub discovery queues.
4. Generate GitHub task with `scripts/linuxdo_surf.py github-plan`.
5. Use GitHub MCP or official GitHub pages to inspect repos and searches.
6. Save GitHub result with `scripts/linuxdo_surf.py github-result`.
7. Merge related GitHub repos and tools back into the frontier.
8. Continue only while the goal and budget justify another batch.

## Output

Chat output remains absorption-friendly: short decision brief plus complete read-post/repo index. Full evidence stays in session/result JSON.

## Stop Rule

For the current goal, stop after five consecutive verification/check rounds find no actionable issue or worthwhile improvement.
