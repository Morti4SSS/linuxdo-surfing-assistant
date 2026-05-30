# Reading Schema

Use this schema when recording Linux.do posts read by Codex. The goal is not beautiful prose; the goal is reusable evidence that can drive the next surfing batch and feed skill management.

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
  "confidence": "high|medium|low"
}
```

`id`, `title`, `url`, and `summary` should be present whenever possible. `author`, reply arrays, feedback, tools, `follow_up_links`, and `confidence` are what make follow-up and evidence extraction useful.

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

## Evidence Rules

Separate positive feedback, negative feedback, and risk notes. A tool being popular is not enough; record why people like it, where it fails, and what it conflicts with. If the thread is mostly noise, record a short summary and set action items empty.

When reading from a user-curated Chrome tab group, preserve the relationship between tabs in the summary, for example "comparison set", "same tool", "opposing view", or "follow-up reference".
