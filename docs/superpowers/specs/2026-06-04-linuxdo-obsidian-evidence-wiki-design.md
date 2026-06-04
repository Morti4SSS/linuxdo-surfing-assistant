# Linux.do 证据驱动 Obsidian 知识库设计

日期：2026-06-04
状态：待用户 review
前置设计：`2026-06-01-linuxdo-obsidian-knowledge-vault-design.md`

## 背景

6 月 1 日的设计已经确定了两层架构：

- 机器持久化层：`state/knowledge/`，负责去重、增量阅读、队列、反馈同步。
- Obsidian 知识层：给人阅读、修改、整理、反馈。

这次修订补上一个核心缺口：Linux.do 帖子、Linux.do 回复和 GitHub issue / discussion 不是稳定资料。它们会错、会被新回复纠正、会过时，也会出现“主帖一般但回复很强”的情况。因此第一版 vault 不能只做资源卡和批次总结，必须引入证据层、观点层和规则层，避免把论坛噪音编译成永久知识。

本设计参考 Karpathy LLM Wiki 的 `raw -> wiki -> schema` 模式，也参考了社区实现中较成熟的机制：`index/log/hot`、lint、citation、人工拒绝反馈、手改保护、增量编译和反论点检查。对本项目而言，这些机制只选择轻量子集，不引入重型自治 wiki。

## 目标

构建一个面向 AI coding / skills / plugins / workflows / agents / tools 的知识库工作流，让 Codex 可以持续从 Linux.do 和 GitHub 中发现线索，同时把内容沉淀为可追溯、可更新、可被人修正的 Obsidian 知识。

成功标准：

- 不重复深读已读 topic，只在必要时读取增量和最小上下文。
- 论坛内容默认作为证据和社区信号，不直接升级为事实。
- 高价值回复、反对意见、竞品比较和作者修正都能被保留下来。
- 资源卡之间通过 Obsidian 双链、标签和对比页形成网络，而不是孤立卡片。
- 人在 Obsidian 里的反馈、拒绝、采用、观察和手改能影响下一轮冲浪。
- 旧结论可以被新证据降级、更新或标为过时。

## 非目标

第一阶段不做：

- 全量迁移旧 30 批历史。
- 全量镜像 Linux.do 帖子。
- 定时主动巡检所有旧 topic。
- 把截图、帖子全文、issue 全文或回复全文长期塞进上下文。
- 上来引入复杂 Obsidian REST / MCP / WebDAV 自动化。
- 让 agent 自动重写人类手改区。
- 建一个独立图谱 UI 或完整数据库产品。

## 设计原则

### 1. 证据优先，知识后置

Linux.do 帖子/回复和 GitHub issue / discussion 中的内容先进入证据层。只有当证据足够、来源清楚、反方已检查、时间风险可接受时，才升级到观点卡、资源卡或工作流页。

### 2. 不把热度当真理

热度、回复数、点赞数用于路由和优先级，不用于直接判定质量。热门帖值得看，是因为它通常能产生更多反对、补充、竞品推荐和实测反馈。

### 3. 保留分歧，不强行综合

遇到推荐 skill、插件、工作流这类多派意见时，不压成“社区认为 X 最好”。必须拆成支持派、反对派、替代方案、适用场景和待验证问题。

### 4. 人类反馈高于 agent 推断

人的反馈可以啰嗦、不标准、甚至暂时不对。Agent 可以润色、整理和提出反驳，但不能静默覆盖 `## 我的反馈`。当人的反馈和 agent 结论冲突时，资源/观点状态应标为需要复核。

### 5. 机器状态和 Obsidian 分离

`state/knowledge/` 是机器运行索引，不直接给人阅读；Obsidian 是人类知识库，不承担全部去重、游标和调度状态。这样人手改 Obsidian 不会破坏 topic 增量读取。

## Vault 结构

建议在当前 vault 上最小演进，而不是立刻大迁移：

```text
LinuxDo-AI-Knowledge/
  AGENTS.md
  CLAUDE.md
  index.md
  log.md
  hot.md

  raw/
    sources/

  evidence/
    linuxdo/
    github/

  claims/
    active/
    disputed/
    stale/

  catalog/
    candidates/
    resources/
    comparisons/
    workflows/
    categories/
    archive/

  feedback/
    preferences/
    decisions/
    rejections/

  inbox/
    sessions/
    review-queue/

  wiki/
    concepts/
    practices/
    notes/
    drafts/
```

当前已有的 `catalog/`、`wiki/`、`inbox/sessions/` 保留。新增重点是 `evidence/`、`claims/`、`feedback/`、`hot.md` 和更强的 `AGENTS.md / CLAUDE.md`。

## 页面类型

### Source Card

保存来源元信息，不保存大段正文。

字段：

- `id`
- `source_type`: `linuxdo_topic | linuxdo_reply | github_repo | github_issue | github_discussion | github_release | github_pr`
- `url`
- `title`
- `author`
- `captured_at`
- `last_seen_at`
- `read_level`
- `state_key`
- `related_evidence`

### Evidence Card

最小可追溯证据。它回答“谁在什么上下文里说了什么，这句话支持还是反对哪个判断”。

字段：

- `id`
- `source_id`
- `claim_refs`
- `stance`: `supports | opposes | qualifies | corrects | reports_failure | reports_success | mentions_alternative`
- `confidence`: `high | medium | low`
- `evidence_kind`: `official | maintainer | firsthand | community_consensus | anecdote | hearsay`
- `summary`
- `minimal_context`
- `risk`

### Claim Card

观点卡不是资源介绍，而是可被证据支持或推翻的判断。

示例：

- “Superpowers 适合高风险正式交付，但不适合小修小改默认全流程。”
- “Trellis 更适合长任务拆解，但不能完全替代轻量需求澄清。”
- “某类中转站推荐帖更像资源积累，不应进入知识层。”

字段：

- `status`: `active | disputed | stale | rejected | watching`
- `claim`
- `supports`
- `opposes`
- `unknowns`
- `counter_arguments`
- `last_reviewed`
- `update_trigger`

### Resource Card

一页一个工具、skill、插件、仓库或服务。资源卡只写稳定资料、使用边界和当前判断；争议细节跳到 Claim/Comparison。

必要章节：

- `## 它是什么`
- `## 适合什么`
- `## 不适合什么`
- `## 当前判断`
- `## 证据摘要`
- `## 相关竞品`
- `## 待验证`
- `## 我的反馈`

### Comparison Page

处理“到底选哪个”的问题。资源卡中只保留极短竞品提示，复杂比较必须进对比页。

必要章节：

- `## 问题`
- `## 选项`
- `## 评价维度`
- `## 各派意见`
- `## 当前建议`
- `## 待验证`

### Feedback Page

保存人的偏好、试用反馈、拒绝原因、采用决策。

类型：

- `preferences/`：长期偏好，例如“不喜欢过重流程”
- `decisions/`：采用、观察、跳过
- `rejections/`：拒绝某个 draft、claim 或资源判断的原因

## AGENTS.md / CLAUDE.md 规则层

根规则文件必须从现在的两条规则升级为可执行 schema。

必须包含：

- vault 结构说明。
- 每种页面何时创建、何时更新。
- source / evidence / claim / resource 的升级条件。
- 论坛内容的可信度规则。
- 争议处理规则。
- 人类反馈和 `## 我的反馈` 保护规则。
- 旧 topic 增量读取规则。
- lint / health check 规则。
- hot cache 更新规则。

关键行为规则：

- 先查 `state/knowledge/topic_index.json` 和相关索引，再决定是否读旧 topic。
- 已读 topic 有新增回复时，只抽新增回复和必要上下文；除非出现强争议、作者修正、链接失效或重大版本变化，不重读整帖。
- 对旧结论做更新时必须保留“旧判断为何成立”和“新证据为何改变它”。
- 任何来自论坛的结论必须带 evidence 状态，不能写成无来源事实。
- 资源页可以重写 agent 区，但不得覆盖 `## 我的反馈`。

## 冲浪读取流程

### 入库前

1. 同步 Obsidian 反馈。
2. 同步可用收藏来源。
3. 读取轻量索引，不读取完整历史。
4. 生成本批候选和阅读级别。

### 阅读时

阅读级别：

- Level 0：只记录元数据或跳过。
- Level 1：主帖 + 少量高信号回复 + 最小上下文。
- Level 2：主帖 + 热门/争议/链接/作者回复 + 对话链上下文。
- Level 3：深读整帖或大部分回复，适合争议、对比、实测串。

DOM/文本优先。只有缺少视觉证据、状态证据、布局语义、图片内容或关键内容时才 render。

### 写入时

每批结束：

1. 更新机器索引。
2. 写 session。
3. 为高价值证据写 evidence。
4. 更新相关 claim/resource/comparison/workflow。
5. 更新 `index.md`、`log.md` 和 `hot.md`。
6. 把需要人判断的内容放入 `inbox/review-queue/`。

## 更新和过时处理

不定时全量巡检旧帖。默认通过以下触发器更新：

- 新冲浪过程中再次遇到已读 topic。
- 收藏/关注来源中出现旧 topic。
- 资源 GitHub 发生明显变更。
- 用户在 Obsidian 中反馈“这个可能过时”。
- 新 evidence 明确反驳旧 claim。

更新结果：

- 小补充：只更新 evidence 和 hot/log。
- 结论变化：更新 claim，资源卡增加“判断变化”。
- 争议未解：claim 移到 `claims/disputed/`。
- 明显过时：claim 移到 `claims/stale/`，资源卡标记 `staleness_risk`。

## Lint / 维护

每 5-10 批或用户要求时运行轻量维护。

检查：

- 孤立资源卡。
- 没有 evidence 的 claim。
- 没有反方检查的强结论。
- `stale` 但仍被 workflow 引用的 claim。
- 资源卡和对比页的双链缺失。
- `## 我的反馈` 是否被保留。
- review queue 是否长期堆积。

维护结果只提出补丁和建议，不自动大规模重写。

## 第一阶段实现范围

应做：

- 新增或更新 vault 规则文件。
- 新增 `evidence/`、`claims/`、`feedback/`、`inbox/review-queue/` 目录。
- 增强 `knowledge-session` 的 Obsidian 写入逻辑，使它能写 evidence/claim/resource/comparison。
- 增强 `feedback-sync`，同步 decisions/preferences/rejections。
- 让 `knowledge-plan` 更明确地使用 Level 0-3 阅读级别和旧 topic 增量策略。

暂不做：

- 复杂图谱 UI。
- 全自动 watchlist 定时巡检。
- WebDAV 同步。
- Obsidian REST/MCP。
- 历史 30 批全量迁移。

## 风险

- Vault 膨胀：用 evidence 最小卡和 review queue 控制，不把整帖搬进 Obsidian。
- 结论失真：所有 claim 必须能追到 evidence。
- 规则太重：AGENTS.md 只保留关键行为；详细模板放到模板文件或参考文档。
- 人类反馈被污染：保留 `## 我的反馈`，agent 只能在别的区归纳“agent 对反馈的理解”。
- token 成本升高：所有启动流程只读 hot/index/state 热索引，不读完整历史。

## 第一阶段决策

- 按“最小演进当前 vault”实施，不重建新 vault。
- `evidence/` 和 `claims/` 作为新增一等目录。
- `AGENTS.md` 作为 Codex 主规则入口，`CLAUDE.md` 与其保持同义镜像或明确指向。
- 不迁移旧 30 批历史；只让新批次先按新结构写入，旧历史后续单独做迁移设计。
