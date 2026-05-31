# Reading Schema

Use this schema when recording Linux.do posts read by Codex. The goal is not beautiful prose; the goal is reusable evidence that can drive the next surfing batch and feed skill management. Detailed notes belong in this structured record; the chat response should stay compact and decision-oriented.

## Required Fields

Each reading should include:

```json
{
  "id": 123,
  "title": "帖子标题",
  "url": "https://linux.do/t/topic/123",
  "author": "username",
  "summary": "一句到一段核心摘要",
  "first_post": "首帖关键内容",
  "historical_replies": [],
  "recent_replies": [],
  "high_value_replies": [],
  "positive_feedback": [],
  "negative_feedback": [],
  "risk_notes": [],
  "comparison_notes": [],
  "tools": [],
  "action_items": [],
  "follow_up_links": [],
  "github_repos": [],
  "json_read": true,
  "render_required": false,
  "render_reasons": [],
  "render_checked": false,
  "image_checked": false,
  "visual_notes": "",
  "confidence_after_render": "",
  "visual_evidence_needed": false,
  "visual_reason": "",
  "visual_review_priority": "low",
  "visual_review_status": "not-needed",
  "visual_review_notes": [],
  "visual_assets": [],
  "confidence": "high|medium|low"
}
```

`id`, `title`, `url`, and `summary` should be present whenever possible. `author`, reply arrays, feedback, tools, `follow_up_links`, `github_repos`, and `confidence` are what make follow-up and evidence extraction useful.

## JSON-First + Render-On-Demand Fields

Linux.do reading should be JSON-first + 按需渲染核验 when possible. `json_read: true` means the post was read through the authenticated `/t/{id}.json` structure. JSON is good for title, body, replies, authors, links, and floor structure, but it cannot prove screenshots, videos, UI, visual workflow, install screens, document layout, or aesthetic claims.

Every JSON reading must decide:

- `render_required`: `true` when the original rendered post or images must be checked before trusting the conclusion.
- `render_reasons`: short reasons such as `命中视觉关键词：WebUI`, `教程/安装/配置/构建内容需要渲染页或截图核验`, or `low/medium confidence 但 value tag 是 马上试`.
- `render_checked`: `true` only after opening the original rendered Linux.do page and checking the relevant visual or layout evidence.
- `image_checked`: `true` only after opening or visually inspecting the relevant images/screenshots/videos/attachments.
- `visual_notes`: compact notes from the rendered page, not a full reread.
- `confidence_after_render`: `high`, `medium`, or `low` after visual核验; leave empty if render was not required or not checked.

Set `render_required=true` for:

- title/body/replies containing 多图, 截图, 图片, 演示, 视频, UI, WebUI, 前端, 审美, 卡片, 可视化, dashboard, 状态栏, 流程图, 执行链路, review-fix, or lite-plan;
- images, videos, attachments, or screenshots where the conclusion depends on visual evidence;
- tutorials, installation, configuration, build, one-click script, Windows, PowerShell, command output, or error-screenshot content;
- Word, Excel, PPT, Markdown, layout, formatting, or document-output effects;
- JSON confidence `low` or `medium` while the value tag or recommendation is `马上试`;
- visual references such as 如图, 看图, 上图, 下图, 截图里, or 效果如下.

可跳过渲染 when the post is pure short Q&A, pure complaint, pure resource entrance, pure model score, low-value/no-action content, or JSON already supports the conclusion and there is no visual, operation-step, or interface judgment.

## Active-Old Posts

For active-old posts, do not only read the newest reply. Capture:

- `first_post`: why the thread started and the original claim or question;
- `historical_replies`: older high-signal replies, accepted answers, corrections, controversy, or long-term usage feedback;
- `recent_replies`: what changed recently and why the old thread became active again;
- `high_value_replies`: replies that contain links, tool names, warnings, comparisons, or concrete workflow steps.

This is the main difference between continuous surfing and simple latest-feed scanning.

## High-Value Reply Shape

Use compact objects:

```json
{
  "id": 456,
  "author": "reply_author",
  "text": "关键回复摘要或摘录",
  "links": ["https://linux.do/t/topic/789"],
  "tools": ["workflow-kit"],
  "why_valuable": "提供替代方案/风险/真实经验"
}
```

Links and tool names should also appear in top-level `tools` when they are central to the post.

Put links worth extending into `follow_up_links`. Do not include every URL; include links that can improve the current goal or reveal better evidence.

Put concrete GitHub repositories worth checking into `github_repos` when the post or replies mention projects, plugins, skills, MCP servers, CLIs, or workflows. Tool names without a repo should still go into `tools`; the state helper can turn them into GitHub search leads.

The older `visual_evidence_needed`, `visual_reason`, `visual_review_priority`, `visual_review_status`, `visual_review_notes`, and `visual_assets` fields remain compatible aliases for old sessions and `visual-review-plan`. New records should prefer the `render_*` fields above, then mirror important notes into the visual fields only when useful.

## Evidence Rules

Separate positive feedback, negative feedback, and risk notes. A tool being popular is not enough; record why people like it, where it fails, and what it conflicts with. If the thread is mostly noise, record a short summary and set action items empty.

When reading from a user-curated Chrome tab group, preserve the relationship between tabs in the summary, for example "comparison set", "same tool", "opposing view", or "follow-up reference".

## Chat Compression

When turning readings into a user-facing answer, compress rather than replay:

- surface the top 3-5 findings by adoption value, risk, or novelty as a brief;
- put each finding into `马上试`, `收藏观察`, or `暂时跳过`;
- include every post read in a read-post index with title, URL, 发现状态, value tag, one-line summary, and expandable detail marker;
- cite key reply points and confidence for posts that contain real findings;
- keep full `first_post`, `historical_replies`, `recent_replies`, and `high_value_replies` in the saved reading record;
- expand a specific item only when the user asks for that item.

每个读过的帖子都 should appear in the user-facing index, even when it had no useful discovery. Mark low-value or noisy posts clearly instead of hiding them.
