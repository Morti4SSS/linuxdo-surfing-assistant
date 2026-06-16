# Linux.do AI 知识库升级方向选择

生成时间：2026-06-07

## 背景

`surf-050` 后，当前知识库已经完成 50 组目标闭环：旧内容补齐已完成，新帖冲浪推进到 `surf-050`，最终 human/ledger audit 为 0 issues，测试 138 OK。现在的问题不再是“能不能持续冲浪”，而是“继续扩大到 1000+ 帖后，知识库是否还能保持可追溯、可反驳、可维护、可被人使用”。

本次检查采用 4 个子代理视角并行评审：

- 数据模型与索引审计。
- 证据、反证与辩证推理审计。
- Obsidian 人读页、反馈闭环与知识工作流审计。
- 持续冲浪流程、风险边界和自动化审计。

外部参考主要来自：

- Karpathy 的 LLM Wiki pattern：raw sources / wiki / schema 三层，ingest / query / lint 三操作，重点是持久 wiki 会在新增来源时更新实体页、修正综合页、标出 contradictions/stale/orphans/gaps，而不是每次 query 重新 RAG。https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- Karpathy gist 衍生讨论：bias-aware lint、stateful scratchpad、page lifecycle、contradicted/stale 状态、graph/json export、claim provenance 等。https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- MemGPT：把长上下文看成分层内存管理，适合映射为 hot context / warm index / cold ledger。https://arxiv.org/abs/2310.08560
- Generative Agents：observation / reflection / planning，以及把经验合成为高层 reflection 再检索使用。https://arxiv.org/abs/2304.03442
- Reflexion：把失败和反馈写成 verbal memory，用于后续决策改进。https://arxiv.org/abs/2303.11366
- GraphRAG：实体图谱 + community summaries，用于全局 sensemaking，而不仅是局部 retrieval。https://www.microsoft.com/en-us/research/publication/from-local-to-global-a-graph-rag-approach-to-query-focused-summarization/
- Argumentation frameworks：用 support / attack 关系处理冲突论证，适合做 claim 支持/反驳边。https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2023.1045663/full

## 当前状态快照

- `state/knowledge/topic_index.json`：约 1277 个 topic。
- `state/knowledge/resource_index.json`：521 个 resource。
- `state/knowledge/claim_index.json`：365 个 claim。
- `state/knowledge/evidence_shards/2026-06.jsonl`：4613 行 evidence；唯一 evidence id 约 1500 个，说明 append-only ledger 保留了历史，但缺少 latest/materialized view。
- `surf-042` 至 `surf-050`：180 条 readings，29 条 new，151 条 metadata_only。
- 近期 readings 的 `counter_evidence` 非空数量为 0。
- evidence ledger 已有 `stance`，包括 `reports_success`、`reports_failure`、`qualifies`、`risk_boundary`、`opposes` 等，但 claim/resource 反向索引仍薄。
- `state/knowledge/user_feedback.json` 有 959 条同步记录，但非空 `feedback` 为 0。
- `topic_update_state.json` 中 freshness 字段不足，`context_pack_latest.json` 的 `topic_updates` 为 0，watchlist 很难自动判断哪些旧帖有新回复。
- 最新 metadata-only 批次中存在 `status=metadata_only` 但 `reading_level=1` 的语义不一致；如果只是 live `/latest` 行，应统一为 `reading_level=0`。

## 子代理共识

1. 当前系统已经有 raw/state/wiki/Obsidian 分层、topic/resource/claim/evidence 四类对象、batch 闭环和质量审计，基础是好的。
2. “0 issues” 代表结构和文案合规，不代表索引健康、claim 证据充分、反证已审或版本未漂移。
3. 下一阶段最重要的是从“证据笔记”升级为“可计算证据系统”：支持边、反驳边、置信度、过期、版本漂移、生命周期事件要能被机器审计。
4. 继续冲 1000+ 帖前，需要批次级 manifest 和 validator，否则浏览器来源、Level/status、脱敏、frontier 消费、audit 结果仍靠人工记流程。
5. Obsidian 人读层可用，但反馈入口有假入口风险：`00_Home` 有 `## 我的反馈`，但 feedback-sync 当前不扫描 `00_Home`。

## 可选升级方向

### 选择 A：索引健康与批次闸门优先

目标：先让系统能发现自己的问题。

内容：

- 新增 `knowledge-index-audit` 只读命令。
- 检查 topic/resource/claim/evidence 引用完整性、重复 id、legacy 状态、空 category、缺 freshness、context_pack 空项。
- 新增 batch manifest：记录 seed/task/read/session/audit/test/consume/checkpoint 的输入输出、topic ids、status/level 分布、browser fallback、redaction scan、frontier pre/post。
- 写入前 validator：Level/status 一致性、metadata-only reason、skip reason、Chrome fallback 必须有失败证据、敏感内容命中时拒写或降级。

优点：成本最低，风险小，马上提高后续 1000+ 帖稳定性。

不足：它是仪表盘和刹车，不直接提升知识推理能力。

适合：马上继续大规模冲浪前。

### 选择 B：Evidence Graph 与辩证 claim 系统

目标：把证据从“文本摘要”升级成“可计算边”。

内容：

- 新增 canonical evidence edge：
  - `evidence_id`
  - `source_id`
  - `target_type`
  - `target_id`
  - `stance`
  - `evidence_kind`
  - `confidence`
  - `observed_at`
  - `expires_at`
  - `source_version`
  - `minimal_context`
  - `risk`
  - `redaction_level`
- 生成 `evidence_by_claim.json`、`evidence_by_resource.json`、`counter_evidence_queue.json`。
- claim 的 `supports/opposes` 改为 evidence id 引用，文本摘要只作为展示缓存。
- claim lifecycle：
  - `proposed`
  - `active`
  - `disputed`
  - `needs_retest`
  - `partially_resolved`
  - `resolved`
  - `superseded`
  - `stale`
  - `rejected`
- 新增 `claim_events.jsonl`，记录每次状态变化、触发证据、置信度变化和原因。
- confidence update：metadata-only 不升高置信度；官方/maintainer/firsthand 增权；失败/修正/反证降权；API/中转/模型/价格类按 TTL 衰减。

优点：最符合 Karpathy LLM Wiki 的“contradictions already flagged / synthesis stays current”，也是辩证证据的核心。

不足：需要 schema migration 和页面更新，实施成本中等。

适合：把知识库从“资料库”变成“判断系统”。

### 选择 C：Karpathy-style Wiki Protocol 与 Lint

目标：把当前经验固化成可迁移协议。

内容：

- 把 `references/reading-schema.md`、`continuous-loop.md`、质量规则、风险边界合并为更强的 wiki schema/protocol。
- 新增 `knowledge-lint`：
  - contradictions
  - stale claims
  - orphan pages
  - missing cross-links
  - missing entity pages
  - source gaps
  - ingestion-order bias
- query 结果可选择回写为 synthesis page、comparison page、decision memo。
- 定期生成 index/log，保留每次 ingest/query/lint 的 append-only 轨迹。

优点：贴近 Karpathy 原始思路，长期可迁移、可复用。

不足：如果没有 A/B 的结构数据支撑，lint 容易停留在 Markdown 文案检查。

适合：在 A 和 B 有基础后做成稳定工作流。

### 选择 D：人读工作台与反馈闭环

目标：让人更容易参与判断，而不是只让 agent 自动跑。

内容：

- `00_Home` 纳入 feedback-sync，或移除 Home 页底部反馈段，避免假入口。
- `user_feedback.json` 增加 `resource`、`claim`、`topic_id`、`decision`、`priority`。
- Feedback 控制台做三列：
  - 想追
  - 暂时不看
  - 明确不要
- metadata-only 页面顶部加明显标识：未复核、不可采用、只作风险信号。
- source / evidence / resource / claim 做双向导航。
- final report 从“收据”升级为“下一步说明书”：下一轮命令、先读页面、需要人工反馈对象、frontier 为空后的续跑策略。

优点：提升使用感，减少反馈写了但不生效的挫败感。

不足：不先解决 evidence graph，反馈仍难精确影响 claim。

适合：让知识库成为日常可读工具。

### 选择 E：Context Memory 分层与 GraphRAG 输出

目标：让知识库能回答全局问题，而不是只做下一批冲浪。

内容：

- MemGPT 式 hot/warm/cold：
  - hot：当前任务 context pack。
  - warm：resource/claim/evidence materialized index。
  - cold：evidence_shards/topic_summaries/session_log。
- GraphRAG 式 community summaries：
  - Agent 工具链
  - Codex 工作流
  - 中转/公益站风险
  - 本地模型/硬件
  - Prompt/上下文管理
  - 视频/图像生成渠道
- 支持全局问题：哪些工具正在升温？哪些 claim 正在被反驳？哪些风险主题反复出现？哪些帖子值得 L1/L2 补读？

优点：会让知识库从“搜资料”升级为“观察趋势与做决策”。

不足：依赖 B 的证据图谱和 A 的健康审计，否则 community summary 可能总结旧噪音。

适合：完成 A/B 后作为能力放大器。

## 推荐选择

推荐选择：**A+B 的最小合体，命名为 Epistemic Integrity Layer（知识完整性层）**。

不要先做一个大而全的重构。最稳的路线是：

1. **先做 A 的只读审计和批次 manifest**，让隐藏问题可见，并防止后续新批次继续制造 level/status、敏感信息、frontier、fallback 的坏状态。
2. **紧接着做 B 的最小 evidence edge 和 counter-evidence queue**，先不迁移所有历史页面，只对新入库和近期高价值对象生成可计算边。
3. **再用 C 的 lint 思路周期性检查 contradictions/stale/orphans/gaps**，把 Karpathy LLM Wiki 的健康维护落实成命令。
4. **最后做 D/E 的人读工作台和 GraphRAG community summaries**，把可计算底层变成可用的阅读和决策体验。

## 推荐实施切片

### Phase 0：只读体检，不改 schema

新增命令：

```bash
python3 tools/linuxdo_surf.py knowledge-index-audit --config config/knowledge_sources.json --output output/linuxdo_surf/index_audit_latest.json
```

输出：

- `topic_update_missing_count`
- `duplicate_resource_candidates`
- `duplicate_evidence_ids`
- `legacy_status_count`
- `empty_category_count`
- `orphan_claims`
- `orphan_resources`
- `broken_evidence_refs`
- `metadata_only_level_mismatch`
- `feedback_fake_entry_count`

验收标准：

- 不改现有入库行为。
- 能稳定复现当前已知问题。
- 报告可直接排序下一步修复优先级。

### Phase 1：批次 manifest 和写入闸门

新增每批：

```text
output/linuxdo_surf/batch_manifest_surf_XXX.json
```

包含：

- discovery source
- selected ids
- read ids
- status counts
- reading_level counts
- metadata_only/skip reasons
- browser attempts
- fallback evidence
- redaction scan
- audit outputs
- test command summary
- frontier pre/post

验收标准：

- `status=metadata_only` 且只来自 `/latest` DOM 行时，必须 `reading_level=0`。
- `skip` 必须有 `skip_reason`。
- Chrome fallback 必须记录内置浏览器失败证据。
- 敏感内容扫描命中高危模式时，拒写或强制 metadata-only。

### Phase 2：最小 Evidence Edge

新增：

```text
state/knowledge/evidence_index.json
state/knowledge/evidence_by_claim.json
state/knowledge/evidence_by_resource.json
state/knowledge/counter_evidence_queue.json
state/knowledge/claim_events.jsonl
```

验收标准：

- 每条 new claim 至少能追到 support evidence edge。
- 每条 `negative_feedback/reports_failure/opposes/corrects` 进入反证边。
- disputed/stale/needs_retest 能进入下一轮 prepare 候选。
- 最终报告新增“新增 claim / 反证 / 置信度变化 / 过期项”段落。

### Phase 3：反馈与人读层修复

最小改动：

- `00_Home` 纳入 feedback-sync 或移除其反馈入口。
- metadata-only 页面顶部加入统一警示。
- `user_feedback.json` 增加目标对象和 decision 字段。
- final report 加“下一步如何使用”。

## 不推荐优先做的事

- 不建议先做漂亮 dashboard。现在缺的是可计算结构，不是展示。
- 不建议先继续大规模冲 1000+，除非先加 batch manifest 和 index audit。
- 不建议把所有历史一次性迁移到新 schema。先对新入库和高价值 watchlist 做增量兼容，再慢慢回填。
- 不建议只扩充 prompt 或文档规则。当前问题已经不是“agent 不知道规则”，而是没有工具门禁和可计算边。

## 一句话决策

如果只能选一个方向：**先做 `knowledge-index-audit` + `batch_manifest`，随后立刻接 `evidence_edge/counter_evidence_queue`。**

这条路线最像 Karpathy LLM Wiki 的工程化版本：raw/source 不变，wiki 可读，schema 约束 agent，lint 维护健康，claim 能被证据支持也能被反证推翻。
