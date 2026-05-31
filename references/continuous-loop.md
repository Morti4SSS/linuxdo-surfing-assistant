# Continuous Loop

Use this reference when the user invokes `/goal`, asks Codex to keep surfing, or wants open-ended Linux.do goldmining.

## Loop

1. Load or create a frontier queue with the state helper.
2. Select the next batch across `new`, `active-old`, and `low-traffic`.
3. Use Codex 内置浏览器 to read each post deeply.
4. Record readings with the reading schema.
5. Extract discovery leads:
   - author-tracking: high-signal authors;
   - comment-reference: Linux.do links and referenced discussions;
   - tool-lookup: tools, skills, plugins, MCP servers, CLI names, workflows;
   - skill-workflow-evidence: community evidence for skill management;
   - github-repo-research: concrete GitHub repositories worth checking;
   - github-search: search queries for tools, skills, plugins, MCP servers, CLIs, and workflows.
6. Save a session. This merges discovery queues back into the frontier.
7. If GitHub evidence is needed, generate a GitHub task with `github-plan`, inspect with GitHub MCP or official GitHub pages, and save with `github-result`.
8. Report a compact checkpoint: best findings, priority buckets, stop/continue reason, and saved artifact path.
9. Continue if the goal is not met and the budget allows it.

For `/goal`, prefer one主一辅策略 rather than a broad hybrid loop. Use `linuxdo-only` when the user wants pure community surfing, `linuxdo-first` when Linux.do discoveries should be verified on GitHub, and `github-first` only when GitHub findings need Linux.do community feedback. `github-only` belongs to GitHub tasks, not Linux.do browser reading.

When a post depends on screenshots, UI/WebUI/TUI, video, tutorial install steps, workflow diagrams, or aesthetic/layout judgment, mark it for visual review instead of pretending JSON text is enough. Keep the default reading loop JSON-first, but let the queue carry `visual_evidence_needed`, `visual_review_priority`, and `visual_review_status` so a later render pass can pick only the posts that truly need it.

## Extension Rule

持续迭代 means each batch can reshape the next batch. If a post mentions another Linux.do thread, a tool, an author, a risk, or a comparison that is relevant to the user's target, add it as a lead. Then 延展冲浪 from that lead rather than staying on the original list.

Do not extend every link. Extend only when it can improve the target:

- better evidence for a tool or skill;
- GitHub repo health, README quality, recent activity, issues, releases, alternatives, and setup cost;
- strong positive or negative community feedback;
- a workflow that solves the user's current bottleneck;
- a reply that names a better alternative;
- an author who repeatedly produces high-signal AI workflow content.

## Stop Conditions

Stop when one of these is true:

- user target is satisfied;
- next batch is empty;
- read budget or wall-clock budget is reached;
- several consecutive batches produce no high-value leads;
- all remaining candidates are duplicates, low confidence, or off target.

When stopping, explain the stop reason and what remains in the frontier. Do not present a stop as final truth; present it as the end of the current surf pass.

Before stopping for no harvest, run one adjustment pass: 切换热度排序, 切换最新排序, search 同义词, and inspect previous readings for follow-up links, author names, alternate tool names, or unresolved risks. If that still produces no useful leads, save the session with that stop reason.

If a previous single-platform session/result has useful unresolved leads, run `backfill-plan` instead of rereading everything. This produces one compact auxiliary task from saved evidence and preserves the original lightweight pass.

If a batch is visually suspicious or visually rich, do not force a full reread. Mark the item, keep the JSON reading, and enqueue a render回看 batch from the saved result/session. The point is to recover visual evidence surgically, not to double the whole surf pass.

## Checkpoint Output

Long `/goal` runs should not create a huge chat report. After each batch, return only:

- 3-5 high-signal findings or "本批无值得吸收的内容" as the top-findings brief;
- priority buckets: `马上试`, `收藏观察`, `暂时跳过`;
- 已读帖子索引: every post read in the batch with title, link, 发现状态, one-line summary, value tag, and expandable marker;
- one-line evidence index for valuable items: key reply point and confidence;
- next lead chosen for extension and why;
- session or evidence file path.

Keep detailed notes in the reading/session files. The final answer should be a decision brief plus a complete 已读帖子索引 and pointers to saved evidence. Expand only the specific item the user asks about.

## Browser Discipline

Linux.do reading depends on saved login state. If Codex 内置浏览器 is not logged in, ask the user to log in. Do not scrape protected content with unauthenticated HTTP. Do not use computer-use for ordinary post reading.

For active-old posts, read historical context. For low-traffic posts, spend limited budget and mark whether the post is worth deeper follow-up.
