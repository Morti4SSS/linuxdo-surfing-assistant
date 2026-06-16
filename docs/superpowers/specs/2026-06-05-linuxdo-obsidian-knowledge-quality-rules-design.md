# Linux.do Obsidian 知识质量与 Token 规则设计

日期：2026-06-05
状态：待用户 review
前置设计：

- `2026-06-01-linuxdo-obsidian-knowledge-vault-design.md`
- `2026-06-04-linuxdo-obsidian-evidence-wiki-design.md`

## 背景

当前 vault 已经有机器状态、Obsidian 结构、旧记录迁移和导读页，但实际阅读暴露出一个更底层的问题：旧冲浪记录被过早包装成“知识库页面”，导致资源卡、分类页和对比页看起来像成品，内容却仍带有旧批次摘要的噪音。

典型问题包括：

- `公益站` 这种大杂类被写成单一资源卡，混合了宣传帖、推荐帖、API 管理工具和中转使用经验。
- `Vibecoding` / `Vibe-Coding`、`ccswitch` / `CC-Switch` 等别名被拆成多张卡。
- 资源卡摘要出现“高相关”“风佬巨作”“v5.0”“zcf”等无上下文词。
- 摘要结尾出现省略号，说明它不是人类可读的知识摘要。
- 对比页只有结论或维度，没有解释为什么、谁在哪里怎么评价、反方是什么。
- 分类页和资源地图使用“权重”，但权重不是用户偏好，也不是质量分。
- 同一帖子在多个页面被复制摘要，可能增加 token，也让后续更新难以合并。
- `Watchlist`、`status`、`feedback`、`tags` 的实际作用不清楚。

如果不先确定知识写入规则，后续读的帖子越多，越难修复这些问题。因此本设计先冻结继续扩张，重新定义信息模型、写入规则、token 策略和质量门槛。

## 目标

本设计的目标是让 Linux.do / GitHub 发现可以持续沉淀，但不会把论坛噪音、旧摘要、重复结论和过时内容变成难以维护的 Obsidian 膨胀。

成功标准：

- Agent 不需要每次读取完整 vault。
- 同一个 source topic 不在多个页面重复长摘要。
- 资源卡只代表一个明确对象，不混合大类、服务集合、经验帖和工具。
- 对比页按“功能相近”比较，而不是把完整 workflow 和局部 skill 乱比。
- 摘要必须保留帖子精华、观点来源和上下文，禁止省略号和无解释黑话。
- 新证据只在改变判断、补足反方、出现新工具、修正旧结论时写入。
- 人类可以通过 `status`、`watchlist`、`## 我的反馈` 影响后续冲浪。
- 旧迁移页面必须被标记为“待重写”或降级为索引，不能伪装成高质量知识。

## 非目标

第一阶段不做：

- 全量重读 611 条旧 topic。
- 把 `_system/sources/` 做成人类阅读主入口。
- 把每个 Linux.do 回复变成 Obsidian 页面。
- 自动定时巡检所有旧帖子。
- 用一个“权重”替代质量判断。
- 让 agent 自动覆盖人类手写反馈。
- 立即把所有候选卡一次性重写成完美版本。

## 核心原则

### 1. Source 只存一次

一个帖子只应该有一个 canonical source page。资源卡、对比页、claim 页只引用这个 source，不重复复制长摘要。

允许在资源卡和对比页里写少量“证据摘要”，但必须是经过提炼的核心观点，不是旧 topic summary 的截断复制。

### 2. Evidence 是可复用证据，不是帖子摘要

Evidence 应回答：

- 谁说的？
- 在哪个帖子或 repo 里说的？
- 支持、反对、修正、补充了什么？
- 对哪个 resource、claim 或 comparison 有影响？
- 可信度和过时风险是什么？

Evidence 不应该只是“这个帖子高相关”。

### 3. Resource Card 只代表一个对象

资源卡不能代表模糊集合。

错误示例：

- `公益站`：太大，混合服务、帖子集合、推荐、风险和管理工具。
- `VS Code`：太泛，应该拆成 VS Code 插件、配置方式、AI coding 入口或具体工具。
- `Vibecoding` 和 `Vibe-Coding`：同义词必须合并。

正确做法：

- 大类概念进入 `Concept`。
- 具体工具或服务进入 `Resource` / `Service`。
- 资源集合进入 `Collection`。
- 帖子本身进入 `Source Topic`。

### 4. Comparison 必须按功能相近比较

不能把“完整 workflow”和“局部 skill”直接对比。

错误示例：

- `Superpowers vs grill-me`

正确示例：

- `Superpowers brainstorming vs grill-me`
- `Trellis session resume vs memory/resume`
- `CCW vs CCG`
- `OpenCode vs Codex CLI`
- `New API vs OneAPI vs CLIProxyAPI`

如果一个页面里有多组不同层级对比，应拆成多个 comparison；允许有重复引用。

### 5. 热度是路由信号，不是质量结论

回复数、出现次数、旧 value_tag、权重只能说明“值得看”或“讨论多”，不能说明“更好”。

人类页面里不应该写含义不明的“权重”。如果保留，必须改名为：

- `讨论信号`
- `出现频次`
- `证据数量`
- `争议热度`

并且必须说明它不是推荐分。

### 6. 摘要必须可读、完整、有上下文

禁止：

- 省略号结尾。
- “高相关”“大佬推荐”“风佬巨作”“v5.0”这类无解释词。
- 只写“提供经验”，不写经验是什么。
- 只写“有人说更好”，不写谁、在哪、为什么。
- 把一个帖子里不同观点压成一句结论。

摘要必须包含：

- 核心观点。
- 适用场景。
- 反方或风险。
- 关键上下文。
- 来源链接或 source 引用。

## 信息模型

### Source Topic

表示一个 Linux.do topic 或 GitHub discussion / issue / repo。

用途：

- 保存来源元数据。
- 保存读取状态。
- 作为证据引用目标。

不用于：

- 直接做人类知识结论。
- 重复承载多个资源卡内容。

建议字段：

- `id`
- `source_type`
- `url`
- `title`
- `author`
- `first_seen_at`
- `last_seen_at`
- `last_read_at`
- `read_reply_count`
- `highest_post_number`
- `related_resources`
- `related_claims`

### Evidence

表示一条可复用证据。

建议字段：

- `id`
- `source_id`
- `resource_refs`
- `claim_refs`
- `comparison_refs`
- `stance`: `supports | opposes | qualifies | corrects | reports_success | reports_failure | mentions_alternative`
- `evidence_kind`: `official | maintainer | firsthand | community_signal | hearsay`
- `confidence`: `high | medium | low`
- `summary`
- `minimal_context`
- `risk`

写法要求：

- `summary` 不超过 180 中文字，但必须能独立读懂。
- `minimal_context` 保存必要上下文，不保存整段原文。
- 每条 evidence 只表达一个观点或一个风险。

### Resource

表示一个具体工具、服务、repo、skill、plugin、模型入口或 workflow 包。

资源卡章节：

```md
## 一句话判断

## 它是什么

## 适合什么

## 不适合什么

## 当前结论

## 关键证据

## 反方与风险

## 相关竞品

## 待验证

## 来源

## 我的反馈
```

关键证据规则：

- 只保留会改变判断的证据。
- 相同结论不重复记录。
- 新证据只有在出现反方、新工具、新版本、事故、修复、价格/额度变化、维护状态变化时追加。

### Concept

表示概念和方法，例如：

- vibecoding
- context engineering
- harness engineering
- prompt injection / context pollution
- skill-first workflow

Concept 不评价具体工具，只解释概念边界、常见误读和相关实践。

### Service

表示中转、公益站、API 网关、模型路由服务。

Service 必须和普通 Resource 分开，因为它们变化快、失效风险高、隐私和稳定性风险高。

Service 卡必须额外包含：

- `稳定性`
- `隐私/安全风险`
- `价格/额度变化风险`
- `是否需要回原文复核`
- `最后验证时间`

### Workflow

表示完整工作流，例如：

- CCW
- CCG
- Trellis
- Superpowers 完整流程
- CodeStable
- BMAD 类多 agent 流程

Workflow 卡不应混入单个 skill 的局部比较。局部能力应进入 Component 或 Comparison。

### Component

表示 workflow 中的局部能力，例如：

- brainstorming
- spec writing
- verification
- memory resume
- test-driven loop

Component 适合做横向对比，例如 `Superpowers brainstorming vs grill-me`。

### Comparison

表示“我该选哪个”的页面。

必要章节：

```md
## 比较问题

## 参与选项

## 评价维度

## 各方观点

## 证据表

## 当前建议

## 为什么

## 不确定性

## 相关页面

## 我的反馈
```

`当前建议` 可以很短，但 `为什么` 必须解释证据链。

### Claim

表示可争议判断。

示例：

- “Superpowers 默认全流程不适合小任务。”
- “中转站推荐帖应该先进入积累层，不应进入知识结论层。”
- “长任务质量主要由验收指标决定，不是只靠模型长跑。”

Claim 必须能被 evidence 支持或反驳。

### Feedback

人的偏好、试用、拒绝、采用理由。

规则：

- `## 我的反馈` 永远保留。
- 人写得啰嗦没关系。
- Agent 可以润色 agent 区域，但不能静默覆盖人类反馈。
- 反馈同步只读变化文件，不全量读 Vault。

## Token 策略

### 热索引优先

任务启动只读取：

- `topic_index.json`
- `topic_update_state.json`
- `resource_index.json`
- `claim_index.json`
- `user_feedback.json`
- `frontier_queue.json`

不读取：

- 完整 Obsidian 页面。
- 完整 source topic。
- 完整旧 `readings_all.json`。

### 页面读取策略

Agent 读页面时按需加载：

1. 先读热索引。
2. 如果要判断资源，读 resource card。
3. 如果 resource card 引用 evidence，再读相关 evidence。
4. 如果 evidence 不够或过期，再读 source topic。
5. 如果 source topic 有新回复，再回网页增量读取。

### 避免重复 token

同一帖子被多个页面引用时，不复制帖子摘要。做法：

- comparison 只写 source link / evidence id。
- resource card 只写关键证据摘要。
- source topic 保存完整来源摘要。
- evidence 保存最小可复用观点。

这样同一 source 可以被多个 resource / comparison 引用，但 agent 只有需要时才打开 source。

### 摘要是否给 AI 看

人类可读页面的摘要主要给人看。Agent 不应该每次读所有摘要。

Agent 合并新内容时只读：

- 当前 resource/comparison 的结构化结论。
- 与新证据相关的 evidence。
- 用户反馈。

如果新证据不改变结论，不写入人类页面，只更新 source/evidence 或 topic 状态。

## Watchlist / Status / Feedback 规则

### Watchlist

`watchlist` 表示关注，不表示采用，也不表示马上重读。

使用规则：

- 感兴趣：`watchlist: true` + 在 `## 我的反馈` 写原因。
- 不感兴趣：不要只取消 watchlist，应写反馈或改 `status`。
- 已读 topic 如果 watchlist 为 true 且出现新回复，计划应倾向 Level 2 增量阅读。
- 资源卡 watchlist 同步到 `resource_index`，作为后续整理信号。

### Status

建议状态：

- `candidate`：候选，默认状态。
- `watching`：观察中。
- `active`：已采用或高信任。
- `deprioritized`：不优先。
- `rejected`：明确拒绝。
- `stale`：可能过时。
- `needs_rewrite`：旧迁移页质量不足，需要重写。
- `needs_verification`：准备采用前必须验证。

### Feedback

反馈写法不要求标准，但建议包含：

- 我感兴趣/不感兴趣。
- 原因。
- 想比较的对象。
- 是否准备试用。
- 是否需要 GitHub 验证。

## 标签策略

### 当前结论

Obsidian 页面 frontmatter tags 主要用于人类筛选，不是功能核心。删除这些 tag 通常不会破坏：

- 反馈同步。
- 已读索引。
- wikilink。
- 复核队列。

但重新生成页面会按规则写回 tags。

### 建议保留

保留真正形成知识网络的标签：

- `#knowledge/workflow`
- `#knowledge/agent-cli`
- `#knowledge/multi-agent`
- `#knowledge/api-relay`
- `#knowledge/context-memory`
- `#knowledge/models`
- `#knowledge/github-verification`
- `#source/linuxdo`
- 未来的 `#source/github`

### 建议移除或降级

这些标签和目录/type 重复，可考虑从生成器里去掉：

- `#home`
- `#guide/reading`
- `#catalog/category`
- `#catalog/comparison`
- `#catalog/candidate`
- `#catalog/workflow`
- `#catalog/resource-map`
- `#review/source-triage`
- `#review/source-reread`

## 文件排序策略

Obsidian 中建议按文件名排序。

需要永远靠前的入口页使用数字前缀：

- `00_首页`
- `00_分类总览`
- `00_资源类型地图`
- `00_知识库概念说明`

不建议依赖创建时间或修改时间排序，因为 agent 自动生成会频繁修改文件。

## 旧数据重整规则

旧迁移页面默认不是成品知识。

第一步应批量标记：

- `status: needs_rewrite`
- `evidence_status: legacy_summary`

优先重写对象：

- 被用户点名的问题卡：`公益站`、`VS Code`、`Vibecoding / Vibe-Coding`。
- 高影响工作流：Superpowers、Trellis、CodeStable、CCW、CCG。
- 高风险服务：中转、公益站、API 网关。
- 被多个 comparison 引用的资源。

重写时不全量重读所有网页。先读：

1. 现有 resource card。
2. 关联 source/evidence。
3. 用户反馈。
4. 只有摘要不足或准备采用时，才回原文。

## 质量门槛

任何人类可读页面不得出现：

- 省略号结尾。
- “高相关”这类旧任务判断。
- 没解释的缩写、人名、版本号。
- 不带上下文的“有人说”。
- 混合多个对象的一张 resource card。
- 权重不解释就展示给人。
- 明明有资源卡却不加 wikilink。

任何 resource card 必须通过：

- 单一对象检查。
- 别名合并检查。
- 来源证据检查。
- 反方/风险检查。
- 待验证检查。
- 可读性检查。

任何 comparison 必须通过：

- 功能相近检查。
- 选项完整性检查。
- 评价维度有实际评价。
- 当前建议有“为什么”。
- 至少包含正向、负向或不确定性之一。

## 实施阶段

### Phase 1：规则落地

- 更新 `AGENTS.md / CLAUDE.md`。
- 更新生成器 schema。
- 更新概念说明页。
- 增加 lint：禁止省略号、禁止“高相关”、检查无上下文黑话。

### Phase 2：索引和别名

- 建 `alias_index.json`。
- 合并 `Vibecoding / Vibe-Coding` 等别名。
- 区分 Concept / Resource / Service / Workflow / Component。

### Phase 3：页面生成器重构

- resource card 不再直接使用旧 topic summary。
- category/comparison 不复制 source 摘要。
- 权重改为 discussion signal 或隐藏。
- watchlist/status/feedback 同步到机器索引。

### Phase 4：重点卡重写

先重写用户已经发现问题的页面：

- `公益站`
- `VS Code`
- `Vibecoding / Vibe-Coding`
- `Superpowers`
- `Trellis`
- `CodeStable`
- `CCW / CCG`
- API 中转与网关相关卡

### Phase 5：新冲浪写入

新读帖子必须按新规则写入，旧规则停止扩散。

每批写入后只更新：

- 新 evidence。
- 被证据改变的 resource / claim / comparison。
- 必要的 source topic 状态。

## 验收标准

结构验收：

- 人类页面没有旧批次词、无上下文词和省略号。
- 资源卡单一对象。
- 大类概念不再混入资源卡。
- 对比页只比较功能相近对象。

Token 验收：

- `knowledge-plan` 不读取完整 vault。
- 更新资源卡不需要读取所有 source topic。
- 同一帖子被多个页面引用时，不复制长摘要。

内容验收：

- 资源卡能独立读懂。
- 每条关键证据能追溯到 source。
- 结论有“为什么”。
- 反方、风险、不确定性被保留。

用户反馈验收：

- 改 `watchlist` 能同步到 resource index。
- 改 `status` 能影响资源状态。
- 写 `## 我的反馈` 能进入 `user_feedback.json`。
- 用户拒绝或不感兴趣的方向不会继续被高优先级推荐。

## 待用户确认

本设计确认后，下一步应写 implementation plan。计划应优先实现：

1. 页面质量 lint。
2. tag 精简生成规则。
3. alias 合并。
4. resource card schema 重写。
5. 对比页 schema 重写。
6. 重点旧卡重写队列。
