# Linux.do Reading Playbook

Use this when actually reading Linux.do with Codex 内置浏览器. The skill exists for Linux.do, so prefer behavior that matches the forum instead of generic web research. The default reading pattern is JSON-first + 按需渲染核验, not pure browser rereading and not blind JSON scraping.

## Starting Points

For a user-selected post, read that post and any directly relevant tab-group neighbors. Preserve how the user grouped the tabs. For a lightweight search or small goldmine task, respect the requested post count and stop after that count with a compact result.

Only `/goal` or an explicit "continue until target" request should enter a next-batch loop. In that mode, each batch can create the next batch through discovered links, tool names, authors, and search terms.

## Reading A Topic

Read in this order:

1. Use authenticated `/t/{id}.json` when possible to capture title, category, tags, original post, replies, authors, links, and floor structure.
2. Author identity and whether they appear to be a repeat high-signal contributor.
3. Accepted answer or high-like replies if visible in JSON or rendered page metadata.
4. Recent replies, especially when an old topic was bumped.
5. Replies containing Linux.do links, tool names, GitHub links, warnings, comparisons, or concrete setup steps.
6. 每帖 JSON 深读后必须判断 `render_required`; if true, open the original rendered page/images before making the final judgment when budget allows.

For active old topics, do not treat the newest reply as the whole story. Capture original context, historical correction, and recent update separately.

Set `render_required=true` when the title, body, or replies contain 多图, 截图, 图片, 演示, 视频, UI, WebUI, 前端, 审美, 卡片, 可视化, dashboard, 状态栏, 流程图, 执行链路, review-fix, lite-plan, tutorial/install/config/build/PowerShell/error-screenshot language, document/layout output claims, or visual references like 如图, 看图, 上图, 下图, 截图里, 效果如下.

可跳过渲染 when the post is pure short Q&A, pure complaint, pure resource entrance, pure model score, or JSON already supports the conclusion and there is no visual, operation-step, or interface judgment.

## No-Harvest Adjustment

If a batch has no useful discoveries, do not immediately stop unless the budget is exhausted. Try one adjustment pass:

- 切换热度排序 to find community-vetted discussions.
- 切换最新排序 to catch emerging tools or fresh replies.
- Search 同义词 and related names, for example "skill", "plugin", "插件", "MCP", "workflow", "工作流", "CLI", "Codex", "Claude Code".
- Revisit previous readings for follow-up links, author names, alternate tool names, and unresolved risks.
- Deep-search one promising old thread if it contains high-signal replies or repeated tool mentions.
- For visually rich posts, do focused render核验 on the saved `render_required` candidate list rather than rereading the whole batch.

Stop after the adjustment pass if it still produces no high-value leads, and record the stop reason.

## What To Save

Save only leads that can drive future action:

- Linux.do topic links worth reading next;
- tool, skill, plugin, MCP server, CLI, workflow, or harness names;
- authors worth tracking;
- positive feedback, negative feedback, risks, and comparisons;
- concrete setup or usage patterns.

Do not save generic praise, shallow summaries, or every link on the page.
