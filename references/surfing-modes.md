# Surfing Modes

## Topic Research

Use when the user provides a topic, for example "Codex 长任务工作流" or "MCP 配置经验". Find posts related to that topic, read deeply, and return a compact research brief with evidence links, key replies, tools mentioned, disagreements, and action items.

## Goldmine

Use when the user has no specific target and wants discovery. Search within AI coding, Codex, Claude Code, skill, plugins, MCP, workflow, harness, CLI, open-source tools, experience reports, and cost-control topics. The output should separate high-value finds from merely noisy or popular posts.

## Skill Feedback

Use when the user provides skill names or wants community feedback for skill management. Search for recommendations, complaints, comparisons, alternatives, and risks. The output should be evidence-shaped and suitable for `references/skill-evidence.md`.

## Skill / Workflow Discovery

Use when the user wants better skills, plugins, CLI tools, workflows, or ways of working. Prioritize practical adoption value: what problem it solves, what setup it needs, whether it overlaps with existing skills, and whether community feedback suggests trying it.

## Channel Choice

- `codex-browser`: default. Use Codex 内置浏览器 and saved Linux.do login state.
- `user-chrome`: use when the user says they already opened or grouped relevant posts.
- `mac-goal`: execution shape for `/goal` continuous loops. It still reads through Codex 内置浏览器 and saved Linux.do login state.

The mode controls what to look for. The channel controls where the reading starts.
