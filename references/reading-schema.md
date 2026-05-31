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

Use the visual review fields for posts whose value depends on rendered pages rather than plain text. Set `visual_evidence_needed` to `true` when the post uses screenshots, video, UI/WebUI/TUI, cards, layouts, charts, tutorial screenshots, installation/configuration screens, workflow diagrams, or aesthetic claims that JSON text cannot verify well. Use `visual_review_status` values like `needed`, `checked`, or `not-needed` and preserve short notes in `visual_review_notes`.

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
