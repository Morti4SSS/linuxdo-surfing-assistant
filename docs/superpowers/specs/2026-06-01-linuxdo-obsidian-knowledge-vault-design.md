# Linux.do 冲浪到 Obsidian 知识库设计

日期：2026-06-01
状态：已批准，已进入 writing plan

## 目标

设计一个轻量系统，让 Codex 持续冲浪 Linux.do，并用 GitHub 做资源验证和补充证据，把高价值发现沉淀到 Obsidian，而不是把 vault 变成论坛归档仓库。

第一版目标：

- 用机器状态减少重复阅读和 token 浪费。
- 把 Linux.do / GitHub 发现沉淀为知识页、资源卡、对比页和工作流页。
- 让人在 Obsidian 中的阅读、修改、反馈反哺后续冲浪优先级。

第一版不导入已有 30 批 / 611 条历史结果。先让新 schema 和流程跑顺，之后再做历史迁移。

## 参考模型

参考 Karpathy 的 LLM Wiki 思路：

- Obsidian 是可编辑知识仓库。
- `CLAUDE.md` 定义知识库 schema 和 agent 行为规则。
- `raw/`、`wiki/`、`index.md`、`log.md` 分离来源、知识、导航和日志。

本设计不照抄 Karpathy 的论文/资料库场景，而是适配 Linux.do 这种不稳定、会更新、会争议的论坛来源。论坛帖子只能先作为证据和线索，不能直接当作知识真理。

## 总体架构

系统分两层：机器持久化层和 Obsidian 知识层。

### 机器持久化层

路径：

```text
/Users/mortisss/Documents/linuxdo/state/knowledge/
```

这层给 Codex 和脚本使用，负责去重、增量阅读、偏好学习和队列管理，不作为主要人类阅读入口。

建议文件：

```text
topic_index.json
topic_update_state.json
source_evidence.jsonl
resource_index.json
claim_index.json
feedback_sync_state.json
user_feedback.json
frontier_queue.json
session_log.jsonl
topic_summaries/
evidence_shards/
archive/
```

机器状态不依赖 Obsidian 文件路径作为唯一身份，而是通过页面 frontmatter 里的稳定 `id` 对齐。

机器状态必须区分“热索引”和“冷历史”，避免每次 goal 启动都把历史阅读记录塞进上下文。

热索引只保存判断下一步需要的最小字段：

- `topic_index.json`：topic id、标题、URL、分类、标签、价值等级、状态、watchlist、最后出现时间、关联资源/claim id。
- `topic_update_state.json`：topic id、已读到的最高楼层或 post id、回复数、最后活动时间、上次阅读级别、已读区间、内容指纹、是否有未解决争议。
- `resource_index.json`：资源 id、名称、主页/GitHub、类别、状态、证据数量、最后验证时间、关联对比页。
- `claim_index.json`：观点 id、简短 claim、支持/反对资源、证据状态、过时风险、未解决问题。
- `frontier_queue.json`：候选 URL、来源、优先级、为什么值得看、下次应采用的阅读级别。

冷历史保存完整或较长的历史材料，但默认不进入上下文：

- `topic_summaries/<topic_id>.json`：单 topic 的旧摘要、关键回复、资源、claim、上次结论。
- `evidence_shards/YYYY-MM.jsonl`：按月份追加原始证据摘要，便于追溯但不全量加载。
- `archive/`：低价值、过期、重复或已浓缩内容的冷存储。
- 旧的 `readings_all.json` 只能作为 legacy cold archive，除非执行迁移、审计或用户明确要求，否则不得在 goal 启动时读取。

当需要判断“这个 topic 是否读过”时，只查热索引；当确实要更新某个已读 topic 时，只读对应 `topic_summaries/<topic_id>.json` 和相关 resource/claim 摘要。

### Obsidian 知识层

建议 vault 结构：

```text
vault/
  CLAUDE.md
  AGENTS.md
  index.md
  log.md

  wiki/
    concepts/
    practices/
    drafts/
    notes/

  catalog/
    resources/
    candidates/
    comparisons/
    workflows/
    categories/
    archive/

  inbox/
    sessions/

  raw/
```

`CLAUDE.md` 是知识库规则和 schema。`AGENTS.md` 是 Codex 入口，指向 `CLAUDE.md`，并补充 Codex 的操作边界。

## 第一版范围

包含：

- Linux.do 冲浪持久化和 Obsidian 写入规则。
- `wiki/`、`catalog/`、`comparisons/`、`workflows/`、`candidates/`、`archive/` 结构。
- Obsidian 反馈同步到机器状态。
- LinuxDo Scripts 收藏 JSON 作为主要个人兴趣入口。
- GitHub 作为资源验证和补证来源。
- 每批 20 帖，一批一写。

不包含：

- 导入已有 30 批历史结果。
- 全量读取旧 `readings_all.json` 作为启动上下文。
- Codex 直接请求 WebDAV 或保存 WebDAV 账号密码。
- 定时主动巡检 watchlist。
- 全量镜像论坛。
- 自动维护所有旧 claim 的真实性。
- Obsidian MCP / REST 集成。
- GitHub 全站主动冲浪。
- 多设备机器状态冲突处理。

## 内容分层

### 知识页：`wiki/`

`wiki/` 放需要学习、理解、复用的思路，不放普通链接收藏。

- `wiki/concepts/`：原理、认知、概念。
- `wiki/practices/`：具体方法和实践。
- `wiki/drafts/`：论坛里提炼出的未成熟想法。
- `wiki/notes/`：小型补充笔记。

适合进入知识层的内容：

- AI coding workflow
- agent 编排方法
- skill 设计原则
- 上下文管理
- vibecoding 实践复盘
- 失败案例和踩坑
- 工具评估方法

论坛来源的知识必须显式保留不确定性，避免写成永久事实。

### 正式资源卡：`catalog/resources/`

一页一个具体资源，例如：

- Codex / Claude skill
- plugin
- MCP server
- GitHub repo
- AI coding 工具
- agent 框架
- 浏览器扩展
- 中转站 / 公益站 / 模型服务
- prompt / workflow 模板

资源卡回答：

- 这是什么？
- 解决什么问题？
- 适合什么场景？
- 有什么限制？
- 社区怎么评价？
- 证据来源是什么？
- 相关竞品是什么？
- 我的反馈是什么？

### 候选资源：`catalog/candidates/`

候选资源是“看起来可能有用，但证据不足”的资源。候选也写 Markdown，方便人在 Obsidian 中阅读、修改和反馈。

满足任一强信号即可晋升正式资源：

- 用户标记有用、想试、已试有效。
- 有实测、复盘、踩坑或失败分析。
- GitHub 活跃且文档清楚。
- 多个独立来源推荐或讨论。
- 补上明确工作流缺口。
- 在高质量对比讨论中反复出现。

满足任一负信号即可降权或归档：

- 用户明确不感兴趣。
- 链接、服务、注册或文档不可用。
- GitHub 停更且无维护 fork。
- 多人反馈踩坑且无解决。
- 与 AI coding / skill / plugin / agent / 效率提升目标不相关。
- 与已有资源重复且没有优势。
- 长期只有推荐语，没有实测证据。

### 对比页：`catalog/comparisons/`

对比页是一等公民，用来回答“这一类东西我该选哪个”。

示例：

- Spec 确定类 Skill 对比
- AI Coding Workflow 框架对比
- Browser Surfing Skill 对比
- Obsidian Knowledge Workflow 对比
- Agent 编排工具对比

对比页整理：

- 评价维度
- 热门选择
- 潜力选择
- 适用场景
- 社区分歧
- 当前建议
- 待验证问题

资源卡可以写简短竞品关系，复杂选择问题进入对比页。

### 工作流页：`catalog/workflows/`

工作流页说明多个工具、资源和实践如何组合成流程。

示例：

- AI Coding Workflow
- Linux.do Surfing Workflow
- Obsidian Knowledge Workflow
- Code Review Workflow

工作流页引用资源卡、对比页和知识页，不重复资源卡细节。

### 分类页：`catalog/categories/`

分类页是按资源类型浏览的入口，例如：

- skills
- plugins
- agents
- MCP servers
- relay services
- GitHub projects
- browser tools
- prompt templates

分类页只做索引，不承担深度评价。

### 归档：`catalog/archive/`

归档保存被淘汰、失效、重复、不适合或过时的资源，避免后续又被当作新发现。

主索引默认不展示 archive 内容，除非需要说明“为什么不选它”。

### `raw/` 和 `inbox/`

`raw/` 不是网页镜像，只保存少量特别重要、需要长期引用的来源摘要或短摘录。

`inbox/sessions/` 每批生成一篇轻量阅读报告。

## 个人兴趣入口

个人兴趣信号只提高阅读优先级，不提高事实可信度。

### 首选入口：LinuxDo Scripts 收藏 JSON

第一版以 LinuxDo Scripts 收藏 JSON 作为主要个人兴趣入口。

已在本机验证：

- 插件手动导出会生成 `bookmarkData.json`。
- 导出 JSON 包含分组、分类、标签、时间戳、标题、URL。
- 插件本地使用 Chrome extension storage 存 `bookmarks` / `bookmarkData`。
- 插件 WebDAV 同步会在配置目录下写类似 `bookmarks.json` 的文件。
- 插件收藏本身支持文件夹、话题分类和话题标签，这些都是高价值的人工筛选信号。

已观察到的导出结构：

```json
[
  {
    "id": 0,
    "name": "默认",
    "list": [
      {
        "cate": "开发调优",
        "sort": 999,
        "tags": ["软件开发", "验证码", "接码平台", "注册机"],
        "timestamp": 1780151443336,
        "title": "gopay 注册机终于搞好了",
        "url": "https://linux.do/t/topic/2273499"
      }
    ],
    "sort": 1
  }
]
```

第一版读取本地 JSON 文件路径。WebDAV 可以负责把插件收藏同步成本地文件，但 Codex 不直接请求 WebDAV，也不保存 WebDAV 账号密码。

插件收藏需要按文件夹组织。建议第一版至少保留这些文件夹或等价标签：

- `AI Coding / Workflow`
- `Skills / Plugins`
- `Agents / MCP`
- `Obsidian / Knowledge`
- `Relay / Models`
- `To Verify`
- `Archive`

文件夹和标签的作用不同：

- 文件夹表示用户主动整理后的主归属。
- 标签表示横向属性，例如 `skill`、`plugin`、`中转站`、`实测`、`争议`、`待验证`。
- 进入插件收藏是强个人兴趣信号，但不直接提高事实可信度。

### 插件收藏的增量读取

插件收藏 JSON 不能每次全量当新内容重读。

第一版需要在机器状态中维护一个收藏入口索引，例如：

```text
bookmark_source_index.json
```

记录：

- `url`
- `topic_id`
- `title`
- `folder`
- `cate`
- `tags`
- `timestamp`
- `content_hash`
- `first_seen_at`
- `last_seen_at`
- `last_processed_at`
- `processing_status`

每次任务启动读取收藏 JSON 时，只做轻量 diff：

- URL 未见过：加入 frontier queue。
- URL 已见过但文件夹、分类、标签或标题变化：更新兴趣信号和优先级，不全文重读 topic。
- URL 已见过且 metadata 无变化：跳过。
- URL 对应 topic 已读但进入更高价值文件夹或新增 `待验证` / `实测` 等标签：提升优先级，遇到时再按已读 topic 增量规则处理。

因此，插件收藏是 frontier seed，不是每次强制阅读清单。

### WebDAV 说明

WebDAV 不是 Linux.do 账号，也不是 Chrome 账号。它是云盘服务提供的第三方访问协议。插件里填写的通常是：

- WebDAV 服务器地址
- 云盘账号或邮箱
- 为该插件生成的应用密码

以坚果云为例，官方帮助说明是在账号安全选项里添加第三方应用密码，再把服务器地址、账号和应用密码填入支持 WebDAV 的第三方应用。坚果云免费版有访问频率限制，每 30 分钟不超过 600 次 WebDAV 请求；免费账户也有每月上传/下载流量限制。

第一版不需要 Codex 直接连接 WebDAV。更稳的方式是：

1. 插件负责导出或同步 `bookmarks.json`。
2. WebDAV 或云盘客户端负责把这个文件同步到本机。
3. Codex 只读取本机配置路径里的 JSON。

这意味着正常使用时不需要每次手动导出；只要插件成功同步到 WebDAV，且本机能拿到同步后的 JSON 文件即可。手动导出的 `bookmarkData.json` 只作为 fallback。

是否需要付费取决于 WebDAV 服务。插件收藏 JSON 很小，坚果云免费额度通常够用；如果后续同步更多大文件、图片或频繁请求，再考虑付费或换服务。

建议配置文件：

```text
config/knowledge_sources.json
```

示例：

```json
{
  "linuxdo_scripts_bookmarks": {
    "enabled": true,
    "path": "/absolute/path/to/bookmarks.json",
    "fallback_download_path": "/Users/mortisss/Downloads/bookmarkData.json",
    "dedupe_by": "url",
    "treat_folders_as_interest_signal": true,
    "treat_tags_as_interest_signal": true
  }
}
```

### 次级入口

- 当前 Chrome 打开的 Linux.do 标签和标签组。
- 用户显式给出的链接。
- 用户点名关注的高价值账号。
- Chrome 专用书签文件夹，仅作为备选。

第一版不扫描普通 Chrome 收藏夹，避免混乱。如果后续使用 Chrome 书签，只读取专用文件夹。

## 批次流程

每批读 20 帖。一次 goal 可以连续跑很多批，但 Obsidian 写入频率是一批一写。

### 任务启动

每次冲浪 goal 启动时：

1. 执行反馈同步：
   - 只读自上次同步后修改过的 Obsidian 文件。
   - 提取 frontmatter、标题、Obsidian 链接、`## 我的反馈`、状态变化、归档移动、对 agent 区块的重要人工修改。
   - 更新 `feedback_sync_state.json`、`user_feedback.json`、`resource_index.json`、`claim_index.json`、`frontier_queue.json`。
2. 加载轻量索引：
   - topic index
   - topic update state
   - resource index
   - claim index
   - frontier queue
3. 加载个人兴趣入口：
   - LinuxDo Scripts JSON / WebDAV 同步到本地的 JSON
   - 当前 Chrome Linux.do 标签或标签组
4. 对 LinuxDo Scripts JSON 做增量 diff：
   - 新 URL 加入 frontier queue。
   - 已见 URL 只更新文件夹、分类、标签等兴趣 metadata。
   - 未变化 URL 不触发重读。

默认不加载 `readings_all.json` 这类重历史文件。

### 阅读新 topic

新 topic 提取：

- topic metadata
- 主帖摘要
- 高信号回复
- 资源提及
- claim 和 counterclaim
- 实测、失败分析、配置细节
- 需要 GitHub 验证的外部链接
- 是否需要进入 watchlist

热度和活跃度用于决定是否更深入看回复区，不直接等于质量。

### 回复区处理

回复是重要证据来源，不只是附属内容。

优先阅读：

- 实测反馈
- 失败报告
- 修复和后续结果
- 替代资源
- 揭示评价维度的分歧
- GitHub / 文档 / 外部证据链接
- 作者补充
- 围绕技术点产生大量互动的回复

### 遇到已读 topic

先查 `topic_update_state.json`。

- 回复数和最后活动时间没变：跳过。
- 普通已读 topic：默认跳过，除非出现强新信号。
- watchlist topic 且有新增回复：只读新增回复和必要上下文。
- 非 watchlist topic 但新增很多或突然相关：轻量采样，再决定是否加入 watchlist。

## 冲浪效率与 token 节流

冲浪侧的目标是：先用低成本信号筛选，再把 token 花在真正可能产出知识、资源、对比和实测证据的 topic 上。

### 候选发现先轻后重

发现阶段优先读取轻量信息：

- 标题
- 分类
- 标签
- 回复数
- 最后活动时间
- 是否在 LinuxDo Scripts 收藏中
- 是否来自当前 Chrome 标签/标签组
- 是否已读
- 是否 watchlist

只有命中兴趣规则或出现强信号时才打开 topic 深读。

### Topic 阅读分级

每个 topic 进入阅读前先选择阅读级别。

```text
Level 0: metadata only
Level 1: 主帖 + 少量高信号回复 + 每条回复的最小上下文
Level 2: 主帖 + 热门/争议/链接/作者回复 + 对话链上下文
Level 3: 深读整帖或大部分回复，适合争议、对比、实测串
```

Level 0 用于明显低相关、已读未变、纯水、纯福利注册、纯收集且无实测的 topic。只记录必要 metadata 或跳过。

Level 1 用于可能有价值但证据还不强的 topic。读取主帖、少量高信号回复，并为每条被引用回复保留最小上下文，避免断章取义。

Level 2 用于明显相关或回复区可能有价值的 topic。读取主帖、热门回复、争议回复、含链接回复、作者回复，并保留必要对话链上下文。

Level 3 用于高价值争议、工具对比、完整实测、长期复盘或直接影响资源选择的 topic。可以深读整帖或大部分回复，但必须说明为什么值得深读。

阅读级别可以在阅读中升降级：如果 Level 1 发现高价值争议，可升到 Level 2；如果打开后发现无实质内容，应降到 Level 0/skip。

### 回复区采样规则

默认不按顺序全读回复。优先采样：

- 高赞或高互动回复
- 作者回复
- 含 GitHub、工具、文档、服务链接的回复
- 包含“试了”“踩坑”“替代”“不推荐”“更新了”“解决了”等信号的回复
- 对前文提出质疑、反驳或补充的回复
- 长帖中的总结型回复
- watchlist topic 的新增回复

当回复依赖前文时，必须补读最小对话链上下文。不要只摘一句回复就形成结论。

### Render 策略

默认使用 DOM、文本、Markdown 导出或页面结构化信息。

只有这些情况才 render 或截图：

- 图片、截图、按钮状态或视觉 UI 是核心证据。
- DOM 文本丢失关键内容。
- 需要验证插件 UI 或浏览器侧边栏状态。
- Markdown 导出比 DOM 抽取更可靠。

已读旧帖默认不 render。只有 watchlist 新增内容、关键视觉证据或抽取失败时才 render。

### 上下文加载限制

每次任务启动只加载轻量索引：

- topic index
- topic update state
- resource index
- claim index
- feedback summary
- frontier queue

默认不加载 `readings_all.json` 或完整历史批次。

处理某个 topic 时，只加载该 topic 的旧摘要、状态、楼层进度和相关 resource/claim 摘要，不加载全局历史。

### 状态瘦身和冷历史

历史增长后，状态文件不能继续向单一大 JSON 膨胀。第一版按以下规则维护：

- 热索引文件必须可被快速读取和人工检查，目标是只保存短字段、id、状态和指针。
- 单 topic 的长摘要、关键回复、证据列表写入 `topic_summaries/<topic_id>.json`，按 topic 读取。
- 批次证据追加到按月份分片的 `evidence_shards/YYYY-MM.jsonl`，避免一个文件无限增长。
- 低价值 topic 只在 `topic_index.json` 留下 `seen + skip_reason + last_seen_at`，不写长摘要。
- 多次出现但一直低价值的 topic 降为 `deprioritized`，后续只看 metadata，除非来自用户收藏或出现强新信号。
- 已沉淀进 Obsidian 的资源/claim 不再依赖完整原始阅读记录，机器状态只保留证据指针和简短摘要。
- 旧 `readings_all.json` 不再追加新内容；后续如需迁移，只做离线 migration，迁移结果进入热索引、topic summary 和 evidence shard。

建议设置轻量维护命令或批末维护步骤：

- 每 5-10 批检查热索引体积和重复项。
- 把连续无用、过期、重复的候选移到 `archive/` 或只保留 skip marker。
- 把多条同义 claim 合并为一个 canonical claim，并保留 alias。
- 把过长的 topic summary 压缩成“主结论 + 关键证据 + 未解决问题 + 指针”。

维护步骤只能读取需要处理的分片或 topic summary，不允许为了维护而加载全部历史。

### 批内缓存和去重

同一批内：

- 同一个 topic 只打开一次。
- 同一个 GitHub repo 只验证一次。
- 同一个资源多次出现时合并证据，不重复建卡。
- 同一个 URL 多次来自插件收藏、Chrome 标签和论坛回复时，只合并兴趣来源。

批末写入时只写变化：

- 新资源
- 新候选
- 新 claim
- 新争议
- 新证据状态
- 新用户兴趣信号
- 新 watchlist 理由

低价值阅读只进入机器状态或 session summary，不生成正式 Obsidian 页面。

### 早停规则

打开 topic 后，如果发现属于以下情况，应快速停止深读：

- 纯水贴或闲聊。
- 纯福利/注册/签到信息，且不影响资源目录。
- 纯列表收集，没有实测、对比、维护状态或上下文。
- 与 AI coding / skill / plugin / agent / workflow / 工具效率目标无关。
- 已读 topic 没有新增回复或状态变化。

早停时可以记录 skip reason，供后续调参。

### 批末写入

每批结束后：

- 更新机器状态。
- 写新候选卡。
- 创建或更新资源卡。
- 必要时更新对比页。
- 为未成熟但有价值的思路创建 wiki draft。
- 必要时更新 category / workflow 索引。
- 创建 session report：

```text
inbox/sessions/YYYY-MM-DD-batch-XXX.md
```

- 追加 `log.md`。

## Watchlist 和增量更新

watchlist 的含义是“再次遇到时不要草率跳过”，不是定时巡检清单。

可进入 watchlist 的对象：

- Linux.do topic
- GitHub issue / discussion / release
- GitHub repo
- 资源卡
- claim 或 comparison question

进入 watchlist 的原因：

- 有未解决争议。
- 有质疑等待回应。
- GitHub issue 影响资源是否可用。
- 正式资源的证据状态不稳定。
- 用户写了“继续关注”。
- 回复区可能继续产生高价值信息。

第一版不在任务启动或批末主动巡检 watchlist。只在这些情况检查：

- 冲浪中再次遇到该 topic / resource / issue。
- 资源验证流程自然触及 GitHub repo 或 issue。
- 用户明确要求复查。

## GitHub 的角色

GitHub 第一版是资源验证和补证来源，不是独立主动冲浪源。

用于验证：

- README / docs：资源到底解决什么问题。
- 最近 commit / release：是否维护。
- issue / discussion：真实问题和修复。
- stars / forks：弱信号，不单独决定质量。
- license / 安装方式：是否适合使用。

GitHub 状态变化会更新证据状态：

- issue open 变 closed。
- release 修复问题。
- repo 变 stale。
- fork 成为事实维护版本。

第一版不做 GitHub trending / topic / 全站搜索式冲浪。

## 证据模型

证据要可追溯，但不搬运全文。

保存：

- 来源 URL
- 来源类型
- topic id 或 repo / issue / release id
- 楼层号、评论号或 release 标识
- 简短证据摘要
- 影响的 claim 或 resource
- 证据状态
- 观察时间

默认不保存长摘录。

证据状态：

```text
supporting
contradicting
open_question
resolved
stale
superseded
mixed
```

示例：

```text
- Linux.do topic: https://linux.do/t/topic/12345
  - posts: #1, #17, #42
  - evidence: #17 认为 Skill B 更适合轻量 spec 澄清；#42 认为 Skill A 更适合长工程任务。
  - status: mixed
```

## 质量判断

### 发现信号

这些让 agent 更愿意点进去看：

- 主题匹配 AI coding / skills / plugins / workflows / vibecoding / tools / relay services / agents。
- 出现在 LinuxDo Scripts 收藏或当前 Chrome 上下文中。
- 回复多或持续活跃。
- 包含实测、复盘、对比、失败分析或配置细节。
- 包含 GitHub 链接或具体工具。
- 高价值用户参与。

### 入库强信号

这些允许内容进入正式资源、对比页或知识页：

- 用户反馈说有用或想试。
- 有实测、复盘、失败分析。
- 多个独立来源讨论。
- GitHub 证据足够健康。
- 补上明确工作流缺口。
- 形成可复用评价维度。
- 出现在认真对比或争议中。

### 降权信号

这些降低优先级或导致归档：

- 用户说不感兴趣。
- 链接、服务或注册不可用。
- repo 明显停更。
- 问题被报告但没有解决。
- 与目标领域不相关。
- 与已有更好资源重复。
- 长期只有推荐语，没有证据。

## 争议处理

不要把不同意见压成一个结论。

推荐帖下出现替代工具、反对意见或多派讨论时，提取：

- 观点派别
- 支持理由
- 反对理由
- 适用场景
- 证据来源
- 共识程度
- 待验证点

资源卡记录该资源自身的评价。对比页整理跨资源的选择维度和场景取舍。

示例：

- `catalog/resources/Superpowers.md` 写 Superpowers 的作用、优势、批评和简短竞品关系。
- `catalog/comparisons/Spec 确定类 Skill 对比.md` 比较 Superpowers brainstorming、轻型提问 skill 和其他 spec 设计方法。

## Obsidian 页面 schema

所有正式页面使用统一最小 frontmatter。

```yaml
---
id: resource:superpowers
type: resource
status: active
tags:
  - catalog/resource
last_verified: 2026-06-01
evidence_status: mixed
staleness_risk: medium
watchlist: true
watch_reason: "存在未解决争议"
---
```

### 稳定 ID

`id` 是稳定身份，文件名和路径可以改。

示例：

- `resource:superpowers`
- `candidate:some-new-skill`
- `comparison:spec-skill-comparison`
- `workflow:ai-coding-workflow`
- `concept:context-engineering`
- `practice:designing-ai-coding-skills`

### 页面类型

第一版允许：

```text
resource
candidate
comparison
workflow
category
concept
practice
draft
note
session
archive
```

### 全局状态

第一版状态：

```text
draft
candidate
active
deprioritized
archived
```

`watchlist` 独立于 `status`，所以一个资源可以同时是 `active` 和 `watchlist: true`。

### 过时风险

页面显式显示：

- `last_verified`
- `evidence_status`
- `staleness_risk`

避免把“曾经成立”的论坛观察误当成“现在成立”。

## 页面模板

### Resource

```markdown
# Resource Name

## Agent 摘要

## 解决什么问题

## 适用场景

## 社区评价

## 相关对比

## 来源证据

## 我的反馈
```

### Candidate

```markdown
# Candidate Name

## 为什么被抓到

## 初步判断

## 缺失证据

## 下一步验证

## 来源证据

## 我的反馈
```

### Comparison

```markdown
# Comparison Name

## 当前结论

## 评价维度

## 热门选择

## 潜力选择

## 分歧与争议

## 适用场景

## 相关资源

## 来源证据

## 我的反馈
```

### Knowledge Page

```markdown
# Knowledge Page

## 核心观点

## 方法

## 适用场景

## 限制与反例

## 来源证据

## 我的反馈
```

### Session Report

```markdown
# YYYY-MM-DD Batch XXX

## 本批范围

## 新发现

## 候选资源

## 资源更新

## 对比/争议

## 只记录为证据的内容

## 跳过与原因

## 下一批建议
```

## 编辑规则

`## 我的反馈` 是用户原始反馈区，Codex 不改。

Codex 可以重写、润色、压缩、合并和重排 `## 我的反馈` 以外的整理区块。

如果用户直接修改了 agent 写的区块，Codex 下次应把这些修改当成新输入信号。Codex 仍可重写整理区，但必须吸收用户意图，不能盲目覆盖。

重要页面改动写入 `log.md`。

如果 Codex 对大范围重写没有把握，应写建议到 `inbox/` 或 `log.md`，不要静默重写很多页面。

## 知识库迭代和维护

Obsidian vault 是人工可读的知识产品，不是机器状态的镜像。长期维护目标是让知识更清晰，而不是把每次冲浪的所有发现都永久展开。

每次 surfing goal 启动前只做轻量反馈同步；每批只写必要增量；知识库整理可以分为三种频率：

- 批末整理：写 session、更新新资源/候选/对比/少量 draft。
- goal 启动整理：读取用户反馈、归档移动、状态修改，把偏好同步进机器状态。
- 周期性维护：用户明确要求或累计多批后再做，重点合并重复页、压缩候选、更新对比结论、处理过时内容。

页面膨胀时优先使用这些动作：

- 资源页保留当前判断、适用场景、主要证据和相关对比，把流水讨论移到来源证据或 session。
- 候选页长期没有新证据时，转为 `deprioritized` 或 `archive`。
- 对比页保留“按场景怎么选”，不罗列所有论坛观点。
- wiki 页只保留可复用思路，具体工具争论放到资源页或对比页。
- session 报告只作为批次日志，不反复改写成百科。

过时或有争议的内容不直接删除，先调整状态：

- 已证伪：页面 `status` 改为 `archived` 或 `deprioritized`，证据 `evidence_status` 改为 `superseded`，保留为什么不再推荐。
- 证据冲突：证据 `evidence_status` 改为 `mixed`，页面保留当前 `status`，写清分歧维度和仍需验证的问题。
- 时间敏感：提高 `staleness_risk`，降低推荐语气。
- 用户不感兴趣：降低优先级，但保留最小索引，避免以后重复当新资源处理。

知识库不追求每个旧页面自动最新。只有当新冲浪再次遇到相关 topic/resource、用户反馈要求复查、或资源验证自然触及它时，才更新对应页面。

## 反馈同步

反馈同步发生在每次 surfing goal 启动前，不在每批之间重复做。

只扫描自上次同步后修改过的文件。

提取：

- frontmatter
- 页面标题
- Obsidian 链接
- `## 我的反馈`
- status 变化
- archive / deprioritize 移动
- 用户对 agent 区块的修改

更新：

- `feedback_sync_state.json`
- `user_feedback.json`
- `resource_index.json`
- `claim_index.json`
- `frontier_queue.json`

默认不扫描整个 vault。

## 配置

第一版使用一个小配置文件。

建议路径：

```text
config/knowledge_sources.json
```

建议字段：

```json
{
  "obsidian_vault_path": "/absolute/path/to/vault",
  "linuxdo_scripts_bookmarks": {
    "enabled": true,
    "path": "/absolute/path/to/bookmarks.json",
    "fallback_download_path": "/Users/mortisss/Downloads/bookmarkData.json",
    "dedupe_by": "url",
    "treat_folders_as_interest_signal": true,
    "treat_tags_as_interest_signal": true
  },
  "chrome_context": {
    "enabled": true,
    "read_current_linuxdo_tabs": true
  },
  "github_verification": {
    "enabled": true
  }
}
```

第一版不在配置中保存 WebDAV 凭证。

## 跨设备边界

Obsidian 内容由用户第三方同步工具同步，可在 Mac / Windows 阅读和编辑。

第一版冲浪执行端以 Mac 为主，因为依赖本机 Chrome 登录态和当前 Linux.do 环境。

机器状态放在当前项目：

```text
/Users/mortisss/Documents/linuxdo/state/knowledge/
```

后续可增加 state export/import 或 Git 备份。第一版不解决多设备机器状态冲突。

## Git 边界

brainstorming skill 默认要求写 spec 并 commit。用户已确认本设计的 Git 处理选择为 `4a`：本地默认不把当前 `output/`、`state/` 大目录纳入提交。

当前 spec 可以上传到已有远端仓库 `Morti4SSS/linuxdo-surfing-assistant` 的新分支中，只包含文档变更，不上传本地历史输出。后续实现再基于该分支或新的实现分支继续。

## 成功标准

进入 implementation plan 前，必须满足：

- spec 定义机器状态层和 Obsidian 层分离。
- spec 定义 `wiki/`、`catalog/`、`comparisons/`、`workflows/`、`candidates/`、`archive/`。
- spec 把 Linux.do 当作不稳定证据，而不是权威知识。
- spec 定义个人兴趣入口，包含 LinuxDo Scripts JSON。
- spec 定义 Obsidian 反馈同步。
- spec 定义不定时巡检的 watchlist。
- spec 定义轻量热索引、冷历史、`readings_all.json` legacy archive 和按 topic 按需加载规则。
- spec 定义状态瘦身、归档浓缩和知识库长期维护规则。
- spec 定义一批一写。
- spec 定义 frontmatter 和页面模板。
- 用户 review 并批准 written spec。

用户批准后，才能进入 writing plan。
