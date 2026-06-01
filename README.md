# Linux.do Surfing Assistant

## 简介

Linux.do Surfing Assistant 是一个面向 Codex 的 Linux.do AI 冲浪助手，用来在有登录态的浏览器环境里按目标发现、筛选和追踪 AI coding workflow、skills、plugins、agent、MCP、工具和经验分享，并把可信、高价值内容沉淀为可复用的 Obsidian 知识库。

项目目标不是做全站爬虫，也不是生成固定日报，而是把论坛和 GitHub 里的零散线索整理成可复读、可反馈、可迭代的个人知识系统：机器侧负责记录读过什么、下一步该读什么；Obsidian 侧负责沉淀知识、资源评价、对比结论和人的反馈。

## 当前已有功能

当前仓库已经包含一个轻量本地 CLI：`tools/linuxdo_surf.py`。

它主要负责：

- 生成 Linux.do 阅读任务包。
- 支持四种任务模式：
  - `research`：围绕指定主题研究。
  - `goldmine`：无目标淘金，寻找高价值 AI coding 线索。
  - `skill-feedback`：查询某些 skill 的社区反馈。
  - `discover`：发现新的 skill、workflow、plugin、MCP、CLI 或工具。
- 支持操控通道标记：
  - `codex-browser`
  - `user-chrome`
  - `mac-goal`
  - `computer-use`
- 根据标题、标签、正文、热度和已读状态给候选 topic 排序。
- 维护轻量已读状态，避免重复生成同一批阅读任务。
- 把阅读结果整理成模式结果或 skill evidence package。

示例：

```bash
python3 tools/linuxdo_surf.py plan \
  --mode research \
  --query "Codex 工作流" \
  --topics output/linuxdo_skill_research/topic_details_top220.json \
  --output output/linuxdo_surf \
  --state state/linuxdo_surf_state.json
```

当前 CLI 只是状态和任务包辅助工具。真实读帖仍依赖 Codex 内置浏览器、用户 Chrome 登录态，或后续的浏览器控制流程。

## 正在开发的功能

正在开发的是第一版 “Linux.do 冲浪到 Obsidian 知识库” 系统。

核心方向：

- 把机器持久化状态和 Obsidian 知识库分开。
- 用轻量热索引减少重复阅读和 token 浪费。
- 把旧的 `readings_all.json` 降级为冷历史，不在普通任务启动时加载。
- 用 `topic_index.json`、`topic_update_state.json`、`resource_index.json`、`claim_index.json`、`frontier_queue.json` 等索引判断下一步读什么。
- 把单 topic 摘要、证据分片和低价值归档拆到冷存储，避免一个大 JSON 文件无限膨胀。
- 读取 LinuxDo Scripts 插件收藏 JSON，作为用户主动筛选过的兴趣入口。
- 生成 Level 0-3 的阅读任务：
  - Level 0：只看 metadata 或跳过。
  - Level 1：主帖 + 少量高信号回复。
  - Level 2：主帖 + 热门/争议/链接/作者回复。
  - Level 3：深读整帖或大部分回复。
- 默认 DOM/文本抽取，只有缺失视觉证据、状态证据、布局语义或关键内容时才 render。
- 每批 20 帖，一批一写：
  - 更新机器状态。
  - 写 Obsidian session report。
  - 创建或更新资源卡、候选资源、对比页、工作流页和 wiki draft。
- 保护 Obsidian 中的 `## 我的反馈`，让人的阅读、修改和偏好反哺后续冲浪。

计划新增命令：

```bash
python3 tools/linuxdo_surf.py knowledge-init --config config/knowledge_sources.json
python3 tools/linuxdo_surf.py feedback-sync --config config/knowledge_sources.json
python3 tools/linuxdo_surf.py bookmark-sync --config config/knowledge_sources.json
python3 tools/linuxdo_surf.py knowledge-plan --config config/knowledge_sources.json --batch-size 20
python3 tools/linuxdo_surf.py knowledge-session --config config/knowledge_sources.json --task output/linuxdo_surf/knowledge_task_latest.json --readings output/linuxdo_surf/knowledge_readings.json
python3 tools/linuxdo_surf.py knowledge-maintain --config config/knowledge_sources.json
```

## 设计文档和计划

- 早期 CLI 设计：[Linux.do 冲浪工具设计](docs/linuxdo-surfing-tool-design.md)
- Obsidian 知识库 spec 目前维护在开发分支：[Linux.do 冲浪到 Obsidian 知识库设计](https://github.com/Morti4SSS/linuxdo-surfing-assistant/blob/codex/obsidian-knowledge-vault-spec/docs/superpowers/specs/2026-06-01-linuxdo-obsidian-knowledge-vault-design.md)
- Obsidian 知识库 implementation plan 目前维护在开发分支：[Linux.do Obsidian Knowledge Vault Implementation Plan](https://github.com/Morti4SSS/linuxdo-surfing-assistant/blob/codex/obsidian-knowledge-vault-spec/docs/superpowers/plans/2026-06-01-linuxdo-obsidian-knowledge-vault.md)

## 开发状态

默认分支 `main` 保存当前可用的轻量 CLI、测试和仓库说明。

知识库设计分支：

```text
codex/obsidian-knowledge-vault-spec
```

这个分支主要保存 spec、implementation plan 和仓库说明。

实际代码实现正在隔离 worktree / 实现分支中推进：

```text
codex/obsidian-knowledge-vault-impl
```

实现完成并通过测试、review 后，再合并回主开发分支。

## 第一版不做什么

第一版明确不做：

- 不导入已有 30 批 / 611 条历史结果。
- 不在启动时全量读取旧 `readings_all.json`。
- 不直接连接 WebDAV，也不保存 WebDAV 账号密码。
- 不定时主动巡检 watchlist。
- 不全量镜像 Linux.do。
- 不做 GitHub 全站主动冲浪。
- 不解决多设备机器状态冲突。

## 测试

当前已有测试：

```bash
python3 -m unittest tests/test_linuxdo_surf.py -q
```

知识库实现完成后，会新增：

```bash
python3 -m unittest tests/test_linuxdo_surf.py tests/test_linuxdo_knowledge.py -q
```
