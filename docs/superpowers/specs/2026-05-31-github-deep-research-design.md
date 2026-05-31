# GitHub Deep Research Design

## Goal

Extend `linuxdo-surfing` so GitHub can verify and extend Linux.do discoveries while still allowing direct GitHub-only research. The flow stays lightweight: choose one primary platform and optionally use the other as a focused auxiliary evidence source. Do not build a default heavy hybrid flow with two parallel agents exchanging findings.

## Scope

In scope:

- Extract GitHub repositories from Linux.do readings, follow-up links, and high-value replies.
- Convert tool, skill, plugin, and workflow names into GitHub search leads.
- Generate a GitHub research task package from the existing frontier queue.
- Generate direct `github-only` task packages from a user query when no Linux.do pass exists.
- Generate `backfill-plan` task packages from old single-platform session/result files.
- Save GitHub research results, update reviewed repo/search state, and merge related repos/tools back into discovery queues.
- Document how Codex should use GitHub MCP or official GitHub pages for repo inspection.

Out of scope:

- Automatic installation, enabling, disabling, or rewriting of skills and plugins.
- Default heavy `hybrid` orchestration with Linux.do and GitHub agents exchanging candidate sets.
- Full GitHub crawling or unauthenticated scraping.

## Strategies

- `linuxdo-only`: use Linux.do browser reading only; record GitHub-looking leads for later.
- `github-only`: use GitHub MCP or official GitHub pages directly from a query or repo list.
- `linuxdo-first`: read Linux.do first, then verify selected projects, skills, plugins, tools, workflows, or repos on GitHub.
- `github-first`: inspect GitHub first, then backfill Linux.do community feedback for selected candidates.

## Data Model

The frontier `discovery_queues` gains:

- `github-repo-research`: concrete repos such as `openai/codex`, with source Linux.do topic links, source GitHub repos, focus, score, and depth.
- `github-search`: search queries derived from tools, skills, plugins, MCP names, and workflow names.

State gains:

- `reviewed_github_repos`
- `reviewed_github_searches`

GitHub readings should preserve repo URL, summary, positive and negative signals, risk notes, related repos, related tools, recommendation, and confidence.

## Workflow

For `linuxdo-first`:

1. Read Linux.do posts with Codex browser.
2. Save session with `scripts/linuxdo_surf.py session`.
3. Extract Linux.do and GitHub discovery queues.
4. Generate GitHub task with `scripts/linuxdo_surf.py github-plan --strategy linuxdo-first`.
5. Use GitHub MCP or official GitHub pages to inspect repos and searches.
6. Save GitHub result with `scripts/linuxdo_surf.py github-result`.
7. Merge related GitHub repos and tools back into the frontier.
8. Continue only while the goal and budget justify another batch.

For `github-only`, run `scripts/linuxdo_surf.py github-plan --strategy github-only --query "<topic>"`, inspect GitHub, and save with `github-result`.

For backfill:

1. Start from an existing `mode_result`, `session`, or `github_result`.
2. Run `scripts/linuxdo_surf.py backfill-plan --source-platform linuxdo|github`; pass `--topics` for GitHub-to-Linux.do backfill when a topic cache is available.
3. Inspect the generated auxiliary task only for selected leads.
4. Save the auxiliary result with the existing `github-result` or `result/session` command.

## Output

Chat output remains absorption-friendly: short decision brief plus complete read-post/repo index. Full evidence stays in session/result JSON.

## Stop Rule

For the current goal, stop after five consecutive verification/check rounds find no actionable issue or worthwhile improvement.
