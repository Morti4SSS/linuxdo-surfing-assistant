# Linux.do Quality Iteration And Current Surf Goal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Linux.do AI 知识库先修到可持续维护状态，继续补齐已有帖子证据；旧内容 refresh 完成后进入新帖冲浪，按每组最多 20 条继续做到第 50 组。

**Architecture:** 先做质量基线和历史内容修复，完成后追加 3 轮复查迭代，直到剩余问题被明确归类为需要网页确认或可排队项。冲浪阶段只使用轻量热索引、context pack、frontier、watchlist、metadata refresh 和人工反馈，不读取旧 `readings_all.json`。浏览器读取优先使用内置浏览器；遇登录、人机验证、加载失败或权限阻塞时按本计划的 Chrome 降级策略执行，并把原因写入批次记录。

**Tech Stack:** Python standard library, `tools/linuxdo_surf.py`, `tools/linuxdo_knowledge/*`, `unittest`, `jq`, `rg`, Codex Browser, Chrome, Obsidian Markdown vault, JSON hot indexes.

---

## 固定约束

- 全程中文。
- 最小改动，不做无关重构。
- 不回滚用户或历史未提交改动。
- 保留所有人读页的 `## 我的反馈`。
- 不把 Linux.do 帖子当成确定真相；必须保存证据、反方、争议、过期风险和待复核项。
- 允许 `Level 0`、`metadata-only` 和 `skip`，跳过项仍要写入状态，避免反复消耗阅读时间。
- 日常路径不得读取旧 `readings_all.json`。
- 每批写入 `state/knowledge/` 和 Obsidian，人读页与 `_system/` 底账继续分层。
- 不使用 token 预算作为停止条件；只按本计划的验收结果、网页读取阻塞或用户新指令暂停。

## 当前恢复点（2026-06-06）

- `old-refresh-014` 已完成 live raw、structured readings、latest 覆盖、入库、human audit 0 issues、ledger audit 0 issues、关键测试和全量测试均通过。
- 第 12 批保留了 2 条 Level 0 skip：`1360514` 为 live JSON not_found + browser blocked；`1145773` 为 Cloudflare challenge + browser blocked；两条都没有用旧摘要替代。
- 第 13 批 20/20 使用内置浏览器 DOM 成功，Chrome fallback 0，skip 0。
- 第 14 批 14 条候选中 9 条使用内置浏览器 DOM 成功，5 条在内置浏览器和 Chrome 均失败后按 Level 0 skip/metadata-only 记录，未使用旧摘要替代。
- 当前 `knowledge-prepare --focus superpowers` 仍生成 8 条 `refresh_light` / reading level 1。
- 最新用户目标恢复为“继续做，做完 50 组”。因此从当前 8 条候选开始执行 `old-refresh-015`，之后继续 prepare/ingest 循环直到累计完成第 50 组。
- 每批继续保持：内置浏览器优先；失败切 Chrome；Chrome 也失败则 Level 0 skip；不读取旧 `readings_all.json`。

## 浏览器策略

每个帖子默认先用内置浏览器读取：

1. 内置浏览器 DOM/JSON/text 提取成功：继续使用内置浏览器。
2. 内置浏览器出现人机验证、登录态缺失、加载失败、权限错误、内容空白或回复缺失：记录 URL、可见状态和失败方法，切换 Chrome 读取该帖。
3. Chrome 读取成功：保存本帖，并在下一个帖子重新尝试内置浏览器。
4. 下一个帖子内置浏览器仍失败：再次切 Chrome。
5. 同一组内连续多次内置浏览器失败，改为本组剩余帖子一直使用 Chrome。
6. 下一组开始仍先尝试内置浏览器；如果同样连续失败，则该组也一直用 Chrome。
7. 若 Chrome 也失败，写入 Level 0 `skip` 或 `metadata-only`，记录 URL、可见状态、失败方法和需要用户处理的动作，不用旧摘要替代。

批次记录必须包含：

```json
{
  "browser_policy": {
    "default": "codex_browser",
    "fallback": "chrome",
    "fallback_reason": "login_or_challenge_or_loading_failure",
    "return_to_default": "next_topic",
    "group_level_fallback": "after_repeated_in_app_failures"
  }
}
```

---

## Task 1: 创建基线快照

**Files:**
- Read: `/Users/mortisss/Documents/linuxdo/config/knowledge_sources.json`
- Read: `/Users/mortisss/Documents/linuxdo/state/knowledge/frontier_queue.json`
- Read/Write: `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/`
- Read: `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/`

- [ ] **Step 1: 记录 git 状态**

Run:

```bash
git status --short --branch
```

Expected: 输出当前脏工作树；不要回滚任何文件。

- [ ] **Step 2: 跑完整测试**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

Expected: 最终结果为 `OK`。如果测试数量变化，以实际输出为准；有失败就先修失败，不进入后续任务。已知 invalid `--channel bad` 的 argparse stderr 只要 final unittest 为 `OK` 就可接受。

- [ ] **Step 3: 跑启动管线**

Run:

```bash
python3 tools/linuxdo_surf.py knowledge-prepare --config config/knowledge_sources.json --batch-size 20 --focus superpowers
```

Expected: exit 0，并生成或刷新：

```text
output/linuxdo_surf/knowledge_prepare_latest.json
output/linuxdo_surf/context_pack_latest.json
output/linuxdo_surf/knowledge_task_latest.json
```

- [ ] **Step 4: 跑 human audit**

Run:

```bash
python3 tools/linuxdo_surf.py knowledge-audit --config config/knowledge_sources.json --output output/linuxdo_surf/quality_audit_human_latest.json
```

Expected: exit 0，报告 `layer` 是 `human`。

- [ ] **Step 5: 跑 ledger audit**

Run:

```bash
python3 tools/linuxdo_surf.py knowledge-audit --config config/knowledge_sources.json --layer ledger --output output/linuxdo_surf/quality_audit_ledger_latest.json
```

Expected: exit 0，报告 `layer` 是 `ledger`。

- [ ] **Step 6: 检查轻量上下文约束**

Run:

```bash
rg -n "readings_all" output/linuxdo_surf/context_pack_latest.json output/linuxdo_surf/knowledge_task_latest.json
jq -r '.history_policy' output/linuxdo_surf/knowledge_task_latest.json
jq '[.watchlist[]? | select(.watchlist != true)] | length' output/linuxdo_surf/context_pack_latest.json
jq '[.feedback[]? | has("feedback")] | any' output/linuxdo_surf/context_pack_latest.json
```

Expected:

```text
rg 无匹配
load_hot_indexes_only
0
false
```

- [ ] **Step 7: 导出问题摘要**

Run:

```bash
jq -r '.issues | group_by(.code) | map({code: .[0].code, count: length}) | sort_by(-.count) | .[] | [.count, .code] | @tsv' output/linuxdo_surf/quality_audit_human_latest.json
jq -r '.issues[:50][] | [.code, .path, .message] | @tsv' output/linuxdo_surf/quality_audit_human_latest.json > output/linuxdo_surf/quality_audit_human_top50.tsv
```

Expected: 得到当前 human 问题数量和前 50 条样本。

---

## Task 2: 清理已知测试污染和不可行动项

**Files:**
- Modify if needed: `/Users/mortisss/Documents/linuxdo/state/knowledge/frontier_queue.json`
- Modify if needed: `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/knowledge_task_latest.json`
- Write: `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/baseline_notes.md`

- [ ] **Step 1: 检查手动测试 topic**

Run:

```bash
rg -n "123456|手动测试" state/knowledge/frontier_queue.json output/linuxdo_surf/knowledge_task_latest.json
```

Expected: 如果存在，确认它只来自 smoke test，不是用户真实 watchlist。

- [ ] **Step 2: 记录测试项处理说明**

Create or update `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/baseline_notes.md` with:

```markdown
# Baseline Notes

## Known Test Artifacts

- `https://linux.do/t/topic/123456` / `手动测试` 是 frontier-add smoke test 留下的测试项，不代表真实阅读意图。
- 处理方式：从真实 frontier 队列移除，避免污染下一轮 `knowledge-plan`。
```

- [ ] **Step 3: 移除 smoke test frontier 项**

Use structured JSON editing, not ad hoc text replacement. After editing, run:

```bash
python3 -m json.tool state/knowledge/frontier_queue.json >/tmp/frontier_queue.check.json
rg -n "123456|手动测试" state/knowledge/frontier_queue.json
```

Expected: JSON 格式合法；`rg` 无匹配。

- [ ] **Step 4: 重新生成启动任务**

Run:

```bash
python3 tools/linuxdo_surf.py knowledge-prepare --config config/knowledge_sources.json --batch-size 20 --focus superpowers
rg -n "123456|手动测试" output/linuxdo_surf/knowledge_task_latest.json
```

Expected: prepare exit 0；`rg` 无匹配。

---

## Task 3: 修复 human audit 当前剩余问题

**Files:**
- Modify: `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/10_Catalog/**`
- Modify: `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/20_Knowledge/**`
- Modify: `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/30_Feedback/**`
- Modify: `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/90_Inbox/review-queue/**`
- Read: `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/quality_audit_human_latest.json`

- [ ] **Step 1: 生成按文件聚合的问题清单**

Run:

```bash
jq -r '.issues | group_by(.path) | map({path: .[0].path, count: length, codes: ([.[].code] | unique | join(","))}) | sort_by(-.count) | .[] | [.count, .path, .codes] | @tsv' output/linuxdo_surf/quality_audit_human_latest.json > output/linuxdo_surf/quality_audit_human_by_path.tsv
```

Expected: 文件按问题数量排序。

- [ ] **Step 2: 第一批优先修对比页**

Select paths matching:

```text
10_Catalog/comparisons/
```

For each page:

- 保留 frontmatter。
- 保留 `## 我的反馈`。
- 补齐该页面类型要求的章节。
- 删除旧模板句，例如“候选资源，当前记录显示它被多次提及”和“是否值得采用要看来源证据、维护状态和反方反馈”。
- 不编造来源；证据不足时写 `needs_source_review` 和具体缺口。

Run after editing:

```bash
python3 tools/linuxdo_surf.py knowledge-audit --config config/knowledge_sources.json --paths-file output/linuxdo_surf/quality_audit_batch_paths.txt --output output/linuxdo_surf/quality_audit_batch_latest.json
jq -r '.issues[]? | [.code, .path, .message] | @tsv' output/linuxdo_surf/quality_audit_batch_latest.json
```

Expected: 本批没有 `template_residue`、`legacy_heading`、`opaque_term`；剩余 `missing_section` 需要立即补齐或写入待复核清单。

- [ ] **Step 3: 第二批修资源页和服务页**

Select paths matching:

```text
10_Catalog/resources/
10_Catalog/services/
```

For each page:

- 明确“是什么 / 适合什么 / 不适合什么 / 反方与风险 / 证据与来源 / 待验证”。
- 对 API 中转、网关、MCP、workflow、skill、agent 保持对象边界，不混类。
- 如果没有足够原文证据，不写成“值得采用”，只写“可观察”或“待复核”。

Run the same batch audit command as Step 2.

- [ ] **Step 4: 第三批修 workflow、concept、component 页面**

Select paths matching:

```text
10_Catalog/workflows/
20_Knowledge/concepts/
20_Knowledge/components/
```

For each page:

- workflow 只和 workflow 比较。
- 局部组件只和局部组件比较。
- concept 页面解释边界、常见误读、适用/不适用场景。
- 泛名页或重复页改成 alias、concept 或 review queue，不保留无证据资源卡。

Run the same batch audit command as Step 2.

- [ ] **Step 5: 第四批处理反馈和 review queue**

Select paths matching:

```text
30_Feedback/
90_Inbox/review-queue/
```

For each page:

- Watchlist 只保留三态说明。
- Review queue 分为“需要处理 / 暂时延后 / 已处理”。
- 复核项必须指向具体证据缺口，不写泛泛说明。

Run the same batch audit command as Step 2.

- [ ] **Step 6: 全量复跑 human audit**

Run:

```bash
python3 tools/linuxdo_surf.py knowledge-audit --config config/knowledge_sources.json --output output/linuxdo_surf/quality_audit_human_after_repair.json
jq -r '.issues | length' output/linuxdo_surf/quality_audit_human_after_repair.json
jq -r '.issues | group_by(.code) | map({code: .[0].code, count: length}) | sort_by(-.count) | .[] | [.count, .code] | @tsv' output/linuxdo_surf/quality_audit_human_after_repair.json
```

Expected: 当前 human audit 问题显著下降；所有剩余项都有路径、原因和后续处理分类。

---

## Task 4: 三轮质量复查迭代

**Files:**
- Read/Write: `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/quality_iteration_round_*.md`
- Modify as needed: `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/**`

- [ ] **Step 1: 复查第 1 轮**

Run:

```bash
python3 tools/linuxdo_surf.py knowledge-audit --config config/knowledge_sources.json --output output/linuxdo_surf/quality_iteration_round_1.json
jq -r '.issues | group_by(.code) | map({code: .[0].code, count: length}) | sort_by(-.count) | .[] | [.count, .code] | @tsv' output/linuxdo_surf/quality_iteration_round_1.json
```

Then inspect top paths and write `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/quality_iteration_round_1.md` with:

```markdown
# Quality Iteration Round 1

## 必须立即修复

## 可以排队稍后处理

## 需要用户打开网页确认
```

Expected: 立即修复项在本轮修掉；网页确认项进入 review queue。

- [ ] **Step 2: 复查第 2 轮**

Run:

```bash
python3 tools/linuxdo_surf.py knowledge-audit --config config/knowledge_sources.json --output output/linuxdo_surf/quality_iteration_round_2.json
jq -r '.issues | group_by(.path) | map({path: .[0].path, count: length, codes: ([.[].code] | unique | join(","))}) | sort_by(-.count) | .[:30][] | [.count, .path, .codes] | @tsv' output/linuxdo_surf/quality_iteration_round_2.json
```

Expected: 本轮重点找第一轮漏掉的跨页面问题、对象混类、重复 alias、比较范围错误。

- [ ] **Step 3: 复查第 3 轮**

Run:

```bash
python3 tools/linuxdo_surf.py knowledge-audit --config config/knowledge_sources.json --output output/linuxdo_surf/quality_iteration_round_3.json
jq -r '.issues | length' output/linuxdo_surf/quality_iteration_round_3.json
```

Expected: 剩余问题全部属于以下三类之一：

```text
需要用户打开网页确认
需要后续冲浪补证
低优先级归档/知识库规模增长问题
```

- [ ] **Step 4: 三轮后刷新导航和维护状态**

Run:

```bash
python3 tools/linuxdo_surf.py knowledge-organize-existing --config config/knowledge_sources.json
python3 tools/linuxdo_surf.py knowledge-audit --config config/knowledge_sources.json --output output/linuxdo_surf/quality_audit_human_post_iteration.json
```

Expected: `00_Home/index.md`、`00_Home/维护状态.md`、review queue 已刷新。

---

## Task 5: 补充已有帖子内容和旧证据

**Files:**
- Read/Write: `/Users/mortisss/Documents/linuxdo/state/knowledge/topic_update_state.json`
- Read/Write: `/Users/mortisss/Documents/linuxdo/state/knowledge/claim_index.json`
- Read/Write: `/Users/mortisss/Documents/linuxdo/state/knowledge/frontier_queue.json`
- Modify: `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/**`

- [ ] **Step 1: 生成旧帖刷新候选**

Run:

```bash
python3 tools/linuxdo_surf.py metadata-refresh --config config/knowledge_sources.json --output output/linuxdo_surf/metadata_refresh_latest.json
python3 tools/linuxdo_surf.py knowledge-prepare --config config/knowledge_sources.json --batch-size 20
```

Expected: 有未读回复、watchlist、disputed claim、needs_retest、partially_resolved、重复发现的 topic 会进入任务候选。

- [ ] **Step 2: 读取旧帖时保留历史上下文**

For every old topic selected:

- 先读主帖和历史上下文。
- 再读新回复。
- 单独记录“原始结论 / 新证据 / 纠错或争议 / 是否改变采用建议”。
- 不只读最新回复。

Expected reading record shape:

```json
{
  "topic_id": 0,
  "url": "",
  "reading_level": 2,
  "update_kind": "old_topic_refresh",
  "original_context": [],
  "new_evidence": [],
  "counter_evidence": [],
  "decision_change": "unchanged|strengthened|weakened|reversed|needs_retest"
}
```

- [ ] **Step 3: 修正已有知识页**

For each changed item:

- 更新资源页、对比页、claim 页或 review queue。
- resolved claim 保留旧反方证据，并写 `resolved_at`、`fix_version`、`verified_at`。
- disputed/needs_retest/partially_resolved 保持刷新触发。

Run:

```bash
python3 tools/linuxdo_surf.py knowledge-session --config config/knowledge_sources.json --task output/linuxdo_surf/knowledge_task_latest.json --readings output/linuxdo_surf/knowledge_readings.json --batch-id old-refresh-001
```

Expected: state 和 Obsidian 同步更新。

- [ ] **Step 4: 旧帖补证后复审**

Run:

```bash
python3 tools/linuxdo_surf.py knowledge-audit --config config/knowledge_sources.json --output output/linuxdo_surf/quality_audit_after_old_refresh.json
python3 tools/linuxdo_surf.py knowledge-prepare --config config/knowledge_sources.json --batch-size 20
```

Expected: 旧帖相关页面无新模板残留；仍缺证据的项目进入 review queue。

---

## Task 5A: 执行当前 old-refresh-013 批次

**Files:**
- Read: `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/knowledge_task_latest.json`
- Write: `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/old_refresh_raw_batch_013.json`
- Write: `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/knowledge_readings_old_refresh_013.json`
- Write: `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/knowledge_readings.json`
- Read/Write: `/Users/mortisss/Documents/linuxdo/state/knowledge/**`
- Modify: `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/**`

- [ ] **Step 1: 确认第 13 批候选**

Run:

```bash
python3 -m json.tool output/linuxdo_surf/knowledge_task_latest.json >/tmp/knowledge_task_latest.check.json
jq -r '.history_policy' output/linuxdo_surf/knowledge_task_latest.json
jq -r '.items[] | [.topic_id, .action, .reading_level, .title] | @tsv' output/linuxdo_surf/knowledge_task_latest.json
```

Expected:

```text
load_hot_indexes_only
20 条候选；当前应以 refresh_light / reading_level 1 为主
```

- [ ] **Step 2: 抓取第 13 批 live raw**

For each topic:

- 先用 Codex in-app browser 读取 DOM/JSON/text。
- 遇人机验证、登录、加载失败、权限错误、空内容、`ERR_BLOCKED_BY_CLIENT` 或回复缺失时，切 Chrome 读取该帖。
- 下一个帖子重新尝试 in-app browser；同组连续多次失败时，本组剩余帖子使用 Chrome。
- Chrome 也失败时，写 `ok:false`、`reading_level:0`、`read_method:"skip_after_live_access_block"`、`attempts`、`visible_state`、`needed_human_action`，不使用旧摘要替代。

Save raw as:

```text
output/linuxdo_surf/old_refresh_raw_batch_013.json
```

Required top-level shape:

```json
{
  "source": "linux.do",
  "observed_at": "ISO-8601 timestamp",
  "browser_policy": {
    "default": "codex_browser",
    "fallback": "chrome",
    "fallback_reason": "login_or_challenge_or_loading_failure",
    "return_to_default": "next_topic",
    "group_level_fallback": "after_repeated_in_app_failures"
  },
  "browser_notes": [],
  "items": []
}
```

- [ ] **Step 3: 校验第 13 批 raw**

Run:

```bash
python3 -m json.tool output/linuxdo_surf/old_refresh_raw_batch_013.json >/tmp/old_refresh_raw_batch_013.check.json
jq '[.items[] | select(.ok == true)] | length' output/linuxdo_surf/old_refresh_raw_batch_013.json
jq '[.items[] | select(.ok != true)] | length' output/linuxdo_surf/old_refresh_raw_batch_013.json
```

Expected: 两个计数相加为 `20`。失败项允许存在，但必须有 attempts、失败原因和 skip/metadata-only 处理。

- [ ] **Step 4: 生成 structured readings**

Use the existing reading-generation pattern from `old-refresh-012`: convert each raw item into an item in `knowledge_readings_old_refresh_013.json`, then copy it to `knowledge_readings.json`.

Required constraints:

- `batch_id`: `old-refresh-013`
- `reading_level`: use `0` only for metadata-only/skip; use `1` or `2` where the raw record contains reusable evidence.
- high-risk topics about license bypass, registration generators, bulk API keys, account abuse, or proxy abuse must be recorded only as risk/boundary evidence, without operational steps.
- preserve uncertainty, disputes, source links, original context, new evidence, counter evidence, and decision change.

Run:

```bash
python3 -m json.tool output/linuxdo_surf/knowledge_readings_old_refresh_013.json >/tmp/knowledge_readings_old_refresh_013.check.json
cp output/linuxdo_surf/knowledge_readings_old_refresh_013.json output/linuxdo_surf/knowledge_readings.json
python3 -m json.tool output/linuxdo_surf/knowledge_readings.json >/tmp/knowledge_readings.check.json
jq '.readings | length' output/linuxdo_surf/knowledge_readings_old_refresh_013.json
```

Expected: both JSON files are valid and contain 20 readings.

- [ ] **Step 5: 禁止旧模板和旧历史入口残留**

Run:

```bash
rg -n "readings_all|旧帖|旧记录|旧冲浪|legacy_summary|候选资源，当前记录显示它被多次提及|是否值得采用要看来源证据|暂无足够可复用证据" output/linuxdo_surf/knowledge_readings_old_refresh_013.json output/linuxdo_surf/knowledge_readings.json
```

Expected: no matches.

- [ ] **Step 6: 入库第 13 批**

Run:

```bash
python3 tools/linuxdo_surf.py knowledge-session --config config/knowledge_sources.json --task output/linuxdo_surf/knowledge_task_latest.json --readings output/linuxdo_surf/knowledge_readings.json --batch-id old-refresh-013
```

Expected: exit 0, state and Obsidian pages update while preserving `## 我的反馈`.

- [ ] **Step 7: 第 13 批审计**

Run:

```bash
python3 tools/linuxdo_surf.py knowledge-audit --config config/knowledge_sources.json --output output/linuxdo_surf/quality_audit_human_after_old_refresh_013.json
python3 tools/linuxdo_surf.py knowledge-audit --config config/knowledge_sources.json --layer ledger --output output/linuxdo_surf/quality_audit_ledger_after_old_refresh_013.json
jq -r '.issues | length' output/linuxdo_surf/quality_audit_human_after_old_refresh_013.json
jq -r '.issues | length' output/linuxdo_surf/quality_audit_ledger_after_old_refresh_013.json
```

Expected: both issue counts are `0`; if not, fix only the failing pages or records, then rerun this step.

- [ ] **Step 8: 第 13 批测试**

Run:

```bash
python3 -m unittest tests.test_linuxdo_knowledge.SessionIngestionTests tests.test_linuxdo_knowledge.KnowledgeQualityRulesTests
python3 -m unittest discover -s tests -p 'test_*.py'
```

Expected: all tests pass. The known argparse stderr from invalid `--channel bad` tests is acceptable only if the final unittest result is `OK`.

- [ ] **Step 9: 重新 prepare 判断下一阶段**

Run:

```bash
python3 tools/linuxdo_surf.py knowledge-prepare --config config/knowledge_sources.json --batch-size 20 --focus superpowers
jq -r '.items[] | [.topic_id, .action, .title] | @tsv' output/linuxdo_surf/knowledge_task_latest.json
```

Expected: if items are still `refresh_light`, continue `Task 5` with the next old-refresh batch; otherwise start `Task 6` only for the current reached new-post group and stop after that group.

---

## Task 6: 继续到第 50 组的新帖冲浪执行

**Files:**
- Read: `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/context_pack_latest.json`
- Read: `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/knowledge_task_latest.json`
- Write: `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/knowledge_readings_batch_*.json`
- Write: `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/surf_batch_*.md`
- Modify: `/Users/mortisss/Documents/linuxdo/state/knowledge/**`
- Modify: `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/**`

- [ ] **Step 1: 批次编号**

Use the next available surf batch id only if `knowledge-prepare` has moved out of `refresh_light` old-topic refresh. Continue batches until the cumulative goal reaches 50 groups:

```text
surf-001
surf-002
...
surf-050
```

Each batch reads up to 20 topics. Continue until the 50-group goal is reached, unless the user gives a newer stop condition.

- [ ] **Step 2: 每组启动**

Run for each group:

```bash
python3 tools/linuxdo_surf.py knowledge-prepare --config config/knowledge_sources.json --batch-size 20
```

Expected: `output/linuxdo_surf/knowledge_task_latest.json` contains up to 20 items and `history_policy` remains `load_hot_indexes_only`.

- [ ] **Step 3: 读取策略**

For each topic in the task:

- Level 0: metadata only or skip when title/category/repeated low-value signal shows low value.
- Level 1: main post plus a few high-signal replies.
- Level 2: main post plus popular/disputed/linked/contextual replies.
- Level 3: deep read only for high-value disputed or implementation-critical threads.

Save skipped item with:

```json
{
  "topic_id": 0,
  "url": "",
  "status": "skipped",
  "reading_level": 0,
  "skip_reason": "low_signal|duplicate|off_topic|insufficient_access"
}
```

- [ ] **Step 4: 浏览器执行**

Apply the browser policy section exactly. Batch summary must include:

```markdown
## Browser Notes

- default: Codex in-app browser
- fallback events:
  - URL:
  - reason:
  - fallback used:
  - returned to in-app on next topic: yes/no
- group-level fallback: yes/no
```

- [ ] **Step 5: 每组写回**

After each batch:

```bash
python3 tools/linuxdo_surf.py knowledge-session --config config/knowledge_sources.json --task output/linuxdo_surf/knowledge_task_latest.json --readings output/linuxdo_surf/knowledge_readings.json --batch-id surf-001
python3 tools/linuxdo_surf.py knowledge-audit --config config/knowledge_sources.json --paths-file output/linuxdo_surf/surf-001-paths.txt --output output/linuxdo_surf/quality_audit_surf-001.json
```

Expected: state、Obsidian 和本批 audit 同步完成。

- [ ] **Step 6: 维护触发**

Run maintain at regular boundaries such as `surf-005`, `surf-010`, ..., `surf-050`:

```bash
python3 tools/linuxdo_surf.py knowledge-maintain --config config/knowledge_sources.json
python3 tools/linuxdo_surf.py knowledge-prepare --config config/knowledge_sources.json --batch-size 20
```

Expected: repeated low-value topics can be deprioritized; watchlist and feedback remain active.

- [ ] **Step 7: 阶段总结**

After `surf-010`, `surf-020`, `surf-030`, `surf-040`, and `surf-050`, write:

```text
output/linuxdo_surf/surf_milestone_010.md
output/linuxdo_surf/surf_milestone_020.md
output/linuxdo_surf/surf_milestone_030.md
output/linuxdo_surf/surf_milestone_040.md
output/linuxdo_surf/surf_milestone_050.md
```

Each milestone must include:

```markdown
# Surf Milestone 010

## 马上试

## 收藏观察

## 暂时跳过

## 需要旧帖补证

## 浏览器失败与降级记录

## 保存路径
```

---

## Task 7: 最终验收和报告

**Files:**
- Write: `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/final_goal_report.md`
- Read/Write: `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/*`
- Read/Write: `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/**`

- [ ] **Step 1: 全量测试**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

Expected: all tests pass.

- [ ] **Step 2: 最终 prepare 和 audit**

Run:

```bash
python3 tools/linuxdo_surf.py knowledge-prepare --config config/knowledge_sources.json --batch-size 20
python3 tools/linuxdo_surf.py knowledge-audit --config config/knowledge_sources.json --output output/linuxdo_surf/quality_audit_human_final.json
python3 tools/linuxdo_surf.py knowledge-audit --config config/knowledge_sources.json --layer ledger --output output/linuxdo_surf/quality_audit_ledger_final.json
```

Expected: all commands exit 0.

- [ ] **Step 3: 最终轻量约束检查**

Run:

```bash
rg -n "readings_all" output/linuxdo_surf/context_pack_latest.json output/linuxdo_surf/knowledge_task_latest.json
jq -r '.history_policy' output/linuxdo_surf/knowledge_task_latest.json
jq '[.watchlist[]? | select(.watchlist != true)] | length' output/linuxdo_surf/context_pack_latest.json
jq '[.feedback[]? | has("feedback")] | any' output/linuxdo_surf/context_pack_latest.json
git diff --check HEAD
```

Expected:

```text
rg 无匹配
load_hot_indexes_only
0
false
git diff --check 无输出
```

- [ ] **Step 4: 最终报告**

Write `/Users/mortisss/Documents/linuxdo/output/linuxdo_surf/final_goal_report.md` with:

```markdown
# Linux.do Knowledge Goal Final Report

## 质量修复

## 三轮复查结果

## 旧帖补证

## 新帖冲浪统计

## 马上试

## 收藏观察

## 暂时跳过

## 需要用户打开网页确认

## 浏览器降级记录

## 保存路径

## 残留风险
```

Expected: 报告能让用户直接决定下一轮采用、观察和跳过对象。

---

## 自检

**Spec coverage:** 已覆盖用户要求的完整 plan 落盘、基线检查、知识库质量迭代、完成后追加 3 轮复查、旧帖修正补充、新帖冲浪做到当前已达组即停、Level 0/metadata-only/skip、内置浏览器优先和 Chrome 降级策略、每批写入 state/Obsidian、不读取旧 `readings_all.json`、最终验证和报告。

**Placeholder scan:** 本计划没有未落地占位表达。需要人工判断的地方都给出明确分类：立即修复、稍后排队、需要用户打开网页确认。

**Type consistency:** 统一使用 `watchlist`、`status`、`feedback_preview`、`history_policy`、`reading_level`、`metadata-only`、`skip_reason`、`batch_id`、`browser_policy`、`quality_audit_*`。
