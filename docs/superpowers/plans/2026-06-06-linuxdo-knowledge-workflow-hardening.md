# Linux.do Knowledge Workflow Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Linux.do 冲浪助手和 Obsidian 知识库从“能沉淀内容”升级为“可低 token 持续冲浪、可人工反馈、可更新迭代、可维护审计”的稳定工作流。

**Architecture:** 保持双层结构：Obsidian 是人读和人改的知识库，`state/knowledge/` 是机器热索引和增量状态。日常冲浪只读取轻量索引和人工反馈，不读取旧 `readings_all.json`；旧帖更新先做 metadata refresh，再按触发原因决定是否回源精读。

**Tech Stack:** Python standard library, existing `tools/linuxdo_surf.py`, `tools/linuxdo_knowledge/*`, `unittest`, Obsidian Markdown frontmatter, JSON hot indexes.

---

## 总流程

日常使用应该长这样：

```text
人在 Obsidian 修改 watchlist/status/我的反馈
  -> knowledge-prepare 自动同步反馈和书签
  -> metadata refresh 轻量检查旧帖回复数/最后活动时间
  -> context pack 只装本轮需要的轻量上下文
  -> knowledge-plan 生成本批阅读任务
  -> Codex 用内置浏览器或 Chrome 读帖
  -> knowledge-session 写入机器底账和人读页
  -> quality-audit 只审本批人读页
  -> 人继续在 Obsidian 阅读、修改、拒绝、采用、观察
```

不要让日常路径变成这样：

```text
每次都读 readings_all.json
每次都全量扫旧帖正文
每次都把 _system/sessions 当成人读页面修
每次都把 status/synced_at 当成正向刷新信号
```

---

## P0：先修地基

P0 的目标是解决当前最容易把系统带偏的四件事：

1. 人工状态太多，用户不知道该改什么。
2. audit 把机器底账和人读页面混在一起，导致清理方向错。
3. 旧帖新回复缺少轻量输入源，增量刷新不可靠。
4. 日常启动命令分散，容易漏跑 `feedback-sync`。

### Task 1: 落地 Watchlist 三态简化

**Files:**
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/feedback.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/context_pack.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/strategy.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/second_pass.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tests/test_linuxdo_knowledge.py`
- Reference: `/Users/mortisss/Documents/linuxdo/docs/superpowers/plans/2026-06-06-watchlist-status-simplification.md`

**Product rule:**

```yaml
# 想追
watchlist: true
status: watching
```

```yaml
# 暂时不看，但不是拉黑
watchlist: false
status: deprioritized
```

```yaml
# 明确不要
watchlist: false
status: rejected
```

- [x] **Step 1: 执行已有三态计划**

按 `/Users/mortisss/Documents/linuxdo/docs/superpowers/plans/2026-06-06-watchlist-status-simplification.md` 的 Task 1-6 执行。

- [x] **Step 2: 验证 feedback-sync 能读到所有主要人读目录**

Run:

```bash
python3 -m unittest tests.test_linuxdo_knowledge.FeedbackSyncTests
```

Expected: PASS。

- [x] **Step 3: 验证 context pack 的 watchlist 只认显式 true**

Run:

```bash
python3 -m unittest tests.test_linuxdo_knowledge.KnowledgeQualityRulesTests.test_context_pack_watchlist_requires_explicit_true
```

Expected: PASS。

- [x] **Step 4: 验证负反馈不会触发刷新**

Run:

```bash
python3 -m unittest tests.test_linuxdo_knowledge.ReadingStrategyTests
```

Expected: PASS，并确认 `deprioritized`、`rejected`、`watchlist: false` 不会因为 `synced_at` 变化进入刷新队列。

- [x] **Step 5: 刷新真实 vault 的导读规则页**

Run:

```bash
python3 tools/linuxdo_surf.py knowledge-organize-existing --config config/knowledge_sources.json
```

Expected: `00_Home` 和 `30_Feedback/decisions/Watchlist-使用规则.md` 只讲三态，不再把 `active/candidate/disputed/adopted` 等 agent 状态当成用户日常手动选项。

### Task 2: 拆分 Quality Audit 层级

**Files:**
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/quality_audit.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/quality.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_surf.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tests/test_linuxdo_knowledge.py`

**Audit layers:**

```text
human        严格审人读页
transitional 轻审 candidates/archive/drafts
ledger       只审 _system/sources/evidence/sessions 的机器字段
batch        只审本批目标页和直接引用页
all          调试用，非日常入口
```

- [x] **Step 1: 写失败测试：默认 audit 不扫描 _system 和 sessions**

Add test in `/Users/mortisss/Documents/linuxdo/tests/test_linuxdo_knowledge.py`:

```python
    def test_quality_audit_default_layer_scans_human_pages_only(self):
        from tools.linuxdo_knowledge.quality_audit import audit_vault

        with TemporaryDirectoryPath() as tmp_path:
            vault = tmp_path / "vault"
            human = vault / "10_Catalog" / "resources" / "Tool.md"
            system = vault / "_system" / "evidence" / "linuxdo" / "topic-1.md"
            session = vault / "90_Inbox" / "sessions" / "session-001.md"
            human.parent.mkdir(parents=True, exist_ok=True)
            system.parent.mkdir(parents=True, exist_ok=True)
            session.parent.mkdir(parents=True, exist_ok=True)
            human.write_text("---\nid: resource:tool\ntype: resource\n---\n# Tool\n", encoding="utf-8")
            system.write_text("# Machine Evidence\n\n## 来源证据\n", encoding="utf-8")
            session.write_text("# Session\n\n## 来源证据\n", encoding="utf-8")

            report = audit_vault(vault)

        paths = {issue["path"] for issue in report["issues"]}
        self.assertIn("10_Catalog/resources/Tool.md", paths)
        self.assertNotIn("_system/evidence/linuxdo/topic-1.md", paths)
        self.assertNotIn("90_Inbox/sessions/session-001.md", paths)
        self.assertEqual(report["layer"], "human")
```

- [x] **Step 2: 实现 path layer 分类**

In `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/quality_audit.py`, add:

```python
HUMAN_PREFIXES = (
    "00_Home/",
    "10_Catalog/resources/",
    "10_Catalog/services/",
    "10_Catalog/workflows/",
    "10_Catalog/comparisons/",
    "10_Catalog/collections/",
    "10_Catalog/categories/",
    "20_Knowledge/concepts/",
    "20_Knowledge/components/",
    "20_Knowledge/claims/",
    "30_Feedback/",
    "90_Inbox/review-queue/",
)

TRANSITIONAL_PREFIXES = (
    "10_Catalog/candidates/",
    "10_Catalog/archive/",
    "20_Knowledge/drafts/",
)

LEDGER_PREFIXES = (
    "_system/",
    "90_Inbox/sessions/",
)


def layer_for_path(relative_path: str) -> str:
    if relative_path.startswith(HUMAN_PREFIXES):
        return "human"
    if relative_path.startswith(TRANSITIONAL_PREFIXES):
        return "transitional"
    if relative_path.startswith(LEDGER_PREFIXES):
        return "ledger"
    return "ignored"
```

Update `audit_vault()` signature:

```python
def audit_vault(vault_path: Path, *, layer: str = "human", paths: list[str] | None = None) -> dict[str, Any]:
```

Behavior:

```text
layer="human"        only scan layer_for_path(path) == "human"
layer="transitional" only scan transitional
layer="ledger"       only scan ledger
layer="all"          scan human/transitional/ledger
paths=[...]          scan only exact relative paths, report layer="batch"
```

- [x] **Step 3: ledger audit 不跑人读文案 lint**

Add function:

```python
def audit_ledger_page(relative_path: str, text: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if relative_path.startswith("_system/sources/") and "source_id" not in text and "url:" not in text:
        issues.append({"path": relative_path, "code": "missing_ledger_identity", "message": "底账页缺少 source_id 或 url"})
    if relative_path.startswith("_system/evidence/") and "source:" not in text and "topic_id:" not in text:
        issues.append({"path": relative_path, "code": "missing_ledger_source", "message": "证据页缺少 source 或 topic_id"})
    return issues
```

Ledger layer should call `audit_ledger_page()` instead of `audit_markdown_page()`。

- [x] **Step 4: CLI 增加 --layer 和 --paths-file**

Modify `/Users/mortisss/Documents/linuxdo/tools/linuxdo_surf.py` `knowledge-audit` parser:

```python
knowledge_audit.add_argument("--layer", choices=("human", "transitional", "ledger", "all"), default="human")
knowledge_audit.add_argument("--paths-file", help="只审文件内列出的 vault 相对路径，一行一个。")
```

When `--paths-file` is passed, read paths and call `audit_vault(..., paths=paths)`。

- [x] **Step 5: 验证默认审计变轻**

Run:

```bash
python3 tools/linuxdo_surf.py knowledge-audit --config config/knowledge_sources.json --output output/linuxdo_surf/quality_audit_human_latest.json
python3 tools/linuxdo_surf.py knowledge-audit --config config/knowledge_sources.json --layer ledger --output output/linuxdo_surf/quality_audit_ledger_latest.json
python3 -m unittest tests.test_linuxdo_knowledge
git diff --check
```

Expected:

```text
human audit 不包含 _system/ 和 90_Inbox/sessions/
ledger audit 不报 template_residue/trailing_ellipsis/legacy_heading 这类人读文案问题
tests OK
git diff --check 无输出
```

### Task 3: 增加旧帖 Metadata Refresh 输入源

**Files:**
- Create: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/metadata_refresh.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/strategy.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_surf.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tests/test_linuxdo_knowledge.py`

**Scope:** 第一版只处理“已有 metadata 输入如何更新索引”，不要求在这个任务里实现真实浏览器抓取。浏览器抓取可以由后续冲浪 worker 把 `{topic_id, reply_count, last_activity_at, title, url}` JSON 传进来。

- [x] **Step 1: 写失败测试：metadata 变化会产生未读回复**

Add test:

```python
    def test_metadata_refresh_updates_topic_state_for_unread_replies(self):
        from tools.linuxdo_knowledge.metadata_refresh import apply_topic_metadata_refresh
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, load_hot_indexes, save_hot_index

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            ensure_knowledge_state(config)
            save_hot_index(
                config,
                "topic_update_state",
                {
                    "topics": {
                        "123": {
                            "topic_id": 123,
                            "title": "旧帖",
                            "url": "https://linux.do/t/topic/123",
                            "read_reply_count": 10,
                            "reply_count": 10,
                            "read_last_activity_at": "2026-06-01T00:00:00+08:00",
                            "last_activity_at": "2026-06-01T00:00:00+08:00",
                            "watchlist": True,
                        }
                    }
                },
            )

            result = apply_topic_metadata_refresh(
                config,
                [
                    {
                        "topic_id": 123,
                        "title": "旧帖",
                        "url": "https://linux.do/t/topic/123",
                        "reply_count": 14,
                        "last_activity_at": "2026-06-06T10:00:00+08:00",
                    }
                ],
                refreshed_at="2026-06-06T10:01:00+08:00",
            )
            indexes = load_hot_indexes(config)
            topic = indexes["topic_update_state"]["topics"]["123"]

        self.assertEqual(result["updated"], 1)
        self.assertEqual(topic["reply_count"], 14)
        self.assertEqual(topic["read_reply_count"], 10)
        self.assertEqual(topic["metadata_refreshed_at"], "2026-06-06T10:01:00+08:00")
```

- [x] **Step 2: 创建 metadata_refresh.py**

Create `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/metadata_refresh.py`:

```python
from __future__ import annotations

from typing import Any

from .config import KnowledgeConfig
from .state import load_hot_indexes, now_iso, save_hot_index


def apply_topic_metadata_refresh(
    config: KnowledgeConfig,
    metadata_items: list[dict[str, Any]],
    *,
    refreshed_at: str | None = None,
) -> dict[str, int]:
    indexes = load_hot_indexes(config)
    topic_state = indexes.setdefault("topic_update_state", {}).setdefault("topics", {})
    updated = 0
    unchanged = 0
    timestamp = refreshed_at or now_iso()

    for item in metadata_items:
        topic_id = _topic_id(item)
        if not topic_id:
            unchanged += 1
            continue
        key = str(topic_id)
        existing = topic_state.setdefault(key, {"topic_id": topic_id})
        before = dict(existing)
        for field in ("title", "url", "reply_count", "last_activity_at"):
            if field in item and item[field] not in (None, ""):
                existing[field] = item[field]
        existing["metadata_refreshed_at"] = timestamp
        if existing != before:
            updated += 1
        else:
            unchanged += 1

    save_hot_index(config, "topic_update_state", indexes["topic_update_state"])
    return {"updated": updated, "unchanged": unchanged}


def _topic_id(item: dict[str, Any]) -> int | None:
    try:
        return int(item.get("topic_id"))
    except (TypeError, ValueError):
        return None
```

- [x] **Step 3: CLI 增加 metadata-refresh**

Modify `/Users/mortisss/Documents/linuxdo/tools/linuxdo_surf.py`:

```python
metadata_refresh = subparsers.add_parser("metadata-refresh", help="把轻量 topic metadata 写入 topic_update_state。")
metadata_refresh.add_argument("--input", required=True, help="包含 topic metadata list 的 JSON 文件。")
metadata_refresh.add_argument("--output", help="写入刷新结果 JSON。")
```

Handler behavior:

```python
with Path(args.input).open("r", encoding="utf-8") as handle:
    payload = json.load(handle)
items = payload.get("items", payload) if isinstance(payload, dict) else payload
result = apply_topic_metadata_refresh(config, items)
```

- [x] **Step 4: 验证 knowledge-plan 能吃到未读回复**

Run:

```bash
python3 -m unittest tests.test_linuxdo_knowledge.ReadingStrategyTests
python3 -m unittest tests.test_linuxdo_knowledge.KnowledgeQualityRulesTests.test_metadata_refresh_updates_topic_state_for_unread_replies
```

Expected: PASS。

### Task 4: 增加 knowledge-prepare 一键启动命令

**Files:**
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_surf.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tests/test_linuxdo_knowledge.py`
- Modify: `/Users/mortisss/.codex/skills/linuxdo-surfing/SKILL.md`
- Modify: `/Users/mortisss/Documents/linuxdo/SKILL.md`

**Command behavior:**

```bash
python3 tools/linuxdo_surf.py knowledge-prepare \
  --config config/knowledge_sources.json \
  --batch-size 20 \
  --focus superpowers
```

Should run:

```text
feedback-sync
bookmark-sync if bookmark export exists
knowledge-context-pack
knowledge-plan
```

- [x] **Step 1: 写失败测试：prepare 输出四个 artifact 路径**

Add test:

```python
    def test_knowledge_prepare_runs_daily_startup_pipeline(self):
        from tools.linuxdo_surf import main

        with TemporaryDirectoryPath() as tmp_path:
            config_path = self.write_knowledge_config(tmp_path)
            exit_code = main(
                [
                    "knowledge-prepare",
                    "--config",
                    str(config_path),
                    "--batch-size",
                    "3",
                    "--focus",
                    "superpowers",
                    "--output-dir",
                    str(tmp_path / "output"),
                ]
            )

            manifest = tmp_path / "output" / "knowledge_prepare_latest.json"

        self.assertEqual(exit_code, 0)
        self.assertTrue(manifest.exists())
```

- [x] **Step 2: 实现 prepare manifest**

Manifest JSON should include:

```json
{
  "feedback_sync": "output/linuxdo_surf/feedback_sync_latest.json",
  "bookmark_sync": "output/linuxdo_surf/bookmark_sync_latest.json",
  "context_pack": "output/linuxdo_surf/context_pack_latest.json",
  "knowledge_task": "output/linuxdo_surf/knowledge_task_latest.json",
  "history_policy": "load_hot_indexes_only"
}
```

- [x] **Step 3: 更新 skill 启动流程**

In `/Users/mortisss/.codex/skills/linuxdo-surfing/SKILL.md`, replace the multi-command startup section with:

```bash
python3 tools/linuxdo_surf.py knowledge-prepare --config config/knowledge_sources.json --batch-size 20
```

Keep the individual commands as fallback/reference below it。

- [x] **Step 4: 验证**

Run:

```bash
python3 -m unittest tests.test_linuxdo_knowledge
python3 tools/linuxdo_surf.py knowledge-prepare --config config/knowledge_sources.json --batch-size 20 --focus superpowers
rg -n "readings_all" output/linuxdo_surf/context_pack_latest.json output/linuxdo_surf/knowledge_task_latest.json
git diff --check
```

Expected:

```text
tests OK
knowledge_prepare_latest.json 存在
rg readings_all 无匹配
git diff --check 无输出
```

---

## P1：提升使用体验和阅读体验

P1 的目标是让你实际用起来更顺手：看到新帖能追，打开 Obsidian 知道从哪读，context pack 不会越来越胖。

### Task 5: 增加 frontier-add 手动追踪入口

**Files:**
- Create or Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/frontier.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_surf.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tests/test_linuxdo_knowledge.py`

**Behavior:**

```bash
python3 tools/linuxdo_surf.py frontier-add \
  --config config/knowledge_sources.json \
  --url https://linux.do/t/topic/123456 \
  --reason "我想追这个 superpowers 讨论"
```

Should add one item into `frontier_queue`:

```json
{
  "topic_id": 123456,
  "url": "https://linux.do/t/topic/123456",
  "reason": "我想追这个 superpowers 讨论",
  "source": "manual",
  "priority": 80
}
```

- [x] **Step 1: 写测试：URL 进入 frontier，不立刻建 Obsidian 页面**

Add test:

```python
    def test_frontier_add_adds_manual_topic_without_creating_vault_page(self):
        from tools.linuxdo_knowledge.frontier import add_manual_frontier_item
        from tools.linuxdo_knowledge.state import load_hot_indexes

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            result = add_manual_frontier_item(
                config,
                url="https://linux.do/t/topic/123456/7",
                reason="想追这个讨论",
                added_at="2026-06-06T12:00:00+08:00",
            )
            indexes = load_hot_indexes(config)

        self.assertEqual(result["topic_id"], 123456)
        self.assertEqual(indexes["frontier_queue"]["items"][0]["source"], "manual")
        self.assertFalse((config.obsidian_vault_path / "10_Catalog").exists())
```

- [x] **Step 2: 实现 add_manual_frontier_item**

Use existing `extract_topic_id()` from `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/bookmarks.py`。

- [x] **Step 3: CLI 接入**

Add parser `frontier-add` in `/Users/mortisss/Documents/linuxdo/tools/linuxdo_surf.py`。

- [x] **Step 4: 验证**

Run:

```bash
python3 -m unittest tests.test_linuxdo_knowledge
python3 tools/linuxdo_surf.py frontier-add --config config/knowledge_sources.json --url https://linux.do/t/topic/123456 --reason "手动测试"
python3 tools/linuxdo_surf.py knowledge-plan --config config/knowledge_sources.json --batch-size 5 --output output/linuxdo_surf/knowledge_task_manual_test.json
```

Expected: 手动 topic 能进入 task。

### Task 6: Context Pack 字段投影和反馈截断

**Files:**
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/context_pack.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tests/test_linuxdo_knowledge.py`

**Rule:**

Context pack 是给 Codex 下一轮启动看的，不是给人完整阅读的。每条只保留必要字段：

```text
id/title/type/status/watchlist/path/url/topic_id/reason/feedback_preview/unread_replies
```

- [x] **Step 1: 写测试：长反馈被截断**

Add test:

```python
    def test_context_pack_truncates_feedback_preview(self):
        from tools.linuxdo_knowledge.context_pack import build_context_pack
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, save_hot_index

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            ensure_knowledge_state(config)
            save_hot_index(
                config,
                "user_feedback",
                {
                    "items": [
                        {
                            "id": "resource:tool",
                            "title": "Tool",
                            "status": "watching",
                            "watchlist": True,
                            "path": "/tmp/Tool.md",
                            "feedback": "很重要。" * 300,
                        }
                    ]
                },
            )

            pack = build_context_pack(config, limit=10)
            item = pack["feedback"][0]

        self.assertIn("feedback_preview", item)
        self.assertNotIn("feedback", item)
        self.assertLessEqual(len(item["feedback_preview"]), 500)
```

- [x] **Step 2: 实现 `_project_item()`**

In `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/context_pack.py`:

```python
PROJECT_FIELDS = (
    "id",
    "title",
    "type",
    "status",
    "watchlist",
    "path",
    "url",
    "topic_id",
    "reason",
    "unread_replies",
    "last_activity_at",
    "reply_count",
    "read_reply_count",
)


def _project_item(item: dict[str, Any]) -> dict[str, Any]:
    projected = {field: item[field] for field in PROJECT_FIELDS if field in item}
    feedback = str(item.get("feedback", "")).strip()
    if feedback:
        projected["feedback_preview"] = feedback[:500]
    return projected
```

Apply projection before returning lists。

- [x] **Step 3: 验证 context pack 大小**

Run:

```bash
python3 tools/linuxdo_surf.py knowledge-context-pack --config config/knowledge_sources.json --focus superpowers --output output/linuxdo_surf/context_pack_latest.json
wc -c output/linuxdo_surf/context_pack_latest.json
rg -n "\"feedback\":" output/linuxdo_surf/context_pack_latest.json
```

Expected:

```text
context_pack_latest.json 保持轻量
没有完整 "feedback" 字段，只有 feedback_preview
```

### Task 7: 收敛首页和导读入口

**Files:**
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/second_pass.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tests/test_linuxdo_knowledge.py`
- Generated vault pages:
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/00_Home/index.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/00_Home/怎么读这个知识库.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/00_Home/全库带读手册.md`
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/30_Feedback/decisions/Watchlist-使用规则.md`

**Reading rule:**

首页只做三类入口：

```text
按主题读
按选择读
采用前复核
```

`怎么读这个知识库.md` 是唯一主导读。`全库带读手册.md` 改成目录说明归档，或从首页弱化，不再和主导读重复。

- [x] **Step 1: 写测试：首页不再堆说明书链接**

Add test that generated home contains the three labels and does not contain more than one direct guide link:

```python
    def test_home_uses_three_entry_reading_paths(self):
        from tools.linuxdo_knowledge.second_pass import build_home_page

        text = build_home_page({"resources": [], "comparisons": [], "workflows": []})

        self.assertIn("按主题读", text)
        self.assertIn("按选择读", text)
        self.assertIn("采用前复核", text)
        self.assertLessEqual(text.count("怎么读这个知识库"), 1)
```

If `build_home_page()` currently has a different signature, adapt the test to the actual helper used in `second_pass.py`。

- [x] **Step 2: 修改生成器**

Keep the guide concise:

```markdown
## 按主题读

- [[10_Catalog/categories/index|分类入口]]

## 按选择读

- [[10_Catalog/comparisons/index|对比入口]]

## 采用前复核

- [[90_Inbox/review-queue/index|复核队列]]
- [[30_Feedback/decisions/Watchlist-使用规则|Watchlist 使用规则]]
```

- [x] **Step 3: 刷新真实 vault**

Run:

```bash
python3 tools/linuxdo_surf.py knowledge-organize-existing --config config/knowledge_sources.json
```

Expected: `00_Home/index.md` 更像入口，不像说明书目录。

---

## P2：更新迭代和长期维护

P2 的目标是让知识库长期增长时不炸：争议能被解决，issue 修复能被记录，候选和复核项不会堆成垃圾山。

### Task 8: Review Queue 生命周期

**Files:**
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/second_pass.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/feedback.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tests/test_linuxdo_knowledge.py`

**Statuses:**

```text
open              还需要处理
deferred          暂时放着
resolved          已处理完
converted_to_page 已转成正式资源/服务/概念/对比页
```

- [x] **Step 1: 写测试：resolved 项不会反复进入首页提醒**

Add test:

```python
    def test_review_queue_resolved_item_is_not_active(self):
        from tools.linuxdo_knowledge.feedback import parse_markdown_page

        with TemporaryDirectoryPath() as tmp_path:
            path = tmp_path / "review.md"
            path.write_text(
                "---\nid: review:item-1\ntype: review\nstatus: resolved\n---\n# Item\n\n## 我的反馈\n\n已处理。\n",
                encoding="utf-8",
            )

            parsed = parse_markdown_page(path)

        self.assertEqual(parsed["status"], "resolved")
```

- [x] **Step 2: 生成 review queue 时按状态分区**

In `second_pass.py`, review queue output should group:

```markdown
## 需要处理
## 暂时延后
## 已处理
```

Do not show `resolved` items in the first group。

- [x] **Step 3: 验证**

Run:

```bash
python3 -m unittest tests.test_linuxdo_knowledge
python3 tools/linuxdo_surf.py knowledge-organize-existing --config config/knowledge_sources.json
```

Expected: review queue 不再像无限提醒列表。

### Task 9: Claim / Dispute / Issue 修复状态流

**Files:**
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/session.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/strategy.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tests/test_linuxdo_knowledge.py`

**Statuses:**

```text
disputed           有争议
needs_retest       声称已修，但缺复测
partially_resolved 部分解决
resolved           已有可信证据解决
superseded         被新工具/新版本替代
```

- [x] **Step 1: 写测试：disputed claim 进入刷新候选**

Add test:

```python
    def test_disputed_claim_related_topic_enters_refresh_candidates(self):
        from tools.linuxdo_knowledge.strategy import build_knowledge_task
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, save_hot_index

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            ensure_knowledge_state(config)
            save_hot_index(
                config,
                "claim_index",
                {"claims": {"claim:tool-risk": {"id": "claim:tool-risk", "status": "disputed"}}},
            )
            save_hot_index(
                config,
                "topic_index",
                {
                    "topics": {
                        "123": {
                            "topic_id": 123,
                            "title": "Tool 风险讨论",
                            "url": "https://linux.do/t/topic/123",
                            "claim_ids": ["claim:tool-risk"],
                        }
                    }
                },
            )

            task = build_knowledge_task(config, batch_size=5, created_at="2026-06-06T12:00:00+08:00")

        self.assertEqual(task["items"][0]["topic_id"], 123)
        self.assertIn("disputed_claim", task["items"][0]["refresh_triggers"])
```

- [x] **Step 2: strategy 纳入 claim_index**

Modify `build_knowledge_task()` to pass `claim_index` into `_refresh_candidates()`。

Trigger rule:

```text
topic.claim_ids intersects claim.status in {"disputed", "needs_retest", "partially_resolved"}
  -> refresh_triggers includes disputed_claim
  -> reading_level at least 2
```

- [x] **Step 3: session 写回不要覆盖旧反方证据**

When a reading says issue is fixed:

```text
保留旧 claim 历史证据
新增 resolved/partially_resolved 状态字段
记录 resolved_at/fix_version/verified_at，如果输入里有这些字段
```

- [x] **Step 4: 验证**

Run:

```bash
python3 -m unittest tests.test_linuxdo_knowledge.ReadingStrategyTests
python3 -m unittest tests.test_linuxdo_knowledge
```

Expected: disputed/needs_retest 会触发回源，但不会全量读旧历史。

### Task 10: Alias / Canonical 注册表

**Files:**
- Create: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/aliases.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/quality.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/structure.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tests/test_linuxdo_knowledge.py`

**Purpose:** 解决 `vibecoding` / `Vibe-Coding`、`CLIProxyAPI` / `CPA`、`opencode` / `OpenCode` 这类重复页和重复资源问题。

- [x] **Step 1: 写测试：别名归一不覆盖人工反馈**

Add test:

```python
    def test_alias_registry_maps_name_to_canonical_id(self):
        from tools.linuxdo_knowledge.aliases import canonicalize_name

        self.assertEqual(canonicalize_name("Vibe-Coding"), "Vibecoding")
        self.assertEqual(canonicalize_name("cli proxy api"), "CPA")
        self.assertEqual(canonicalize_name("opencode"), "OpenCode")
```

- [x] **Step 2: 创建 aliases.py**

```python
from __future__ import annotations


ALIASES = {
    "vibe-coding": "Vibecoding",
    "vibecoding": "Vibecoding",
    "cli proxy api": "CPA",
    "cliproxyapi": "CPA",
    "cpa": "CPA",
    "opencode": "OpenCode",
    "open code": "OpenCode",
}


def canonicalize_name(name: str) -> str:
    normalized = " ".join(name.strip().replace("_", " ").replace("-", " ").lower().split())
    compact = normalized.replace(" ", "")
    if normalized in ALIASES:
        return ALIASES[normalized]
    if compact in ALIASES:
        return ALIASES[compact]
    return name.strip()
```

- [x] **Step 3: quality.py 使用统一入口**

Move existing alias normalization logic to call `canonicalize_name()`。

- [x] **Step 4: 验证**

Run:

```bash
python3 -m unittest tests.test_linuxdo_knowledge
```

Expected: alias 测试通过，现有别名测试不回退。

### Task 11: Vault 增长预算和归档策略

**Files:**
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/second_pass.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/quality_audit.py`
- Modify: `/Users/mortisss/Documents/linuxdo/tests/test_linuxdo_knowledge.py`
- Generated vault page:
  - `/Users/mortisss/Documents/Obsidian/LinuxDo-AI-Knowledge/00_Home/维护状态.md`

**Budgets:**

```text
日常 context pack 目标 < 20KB
单批新建人读页 <= 20
单批 review queue 新增 <= 80
sessions 只保留近 30 天强入口，其余靠索引找
_system/evidence/source 默认冷藏，不出现在首页导读
```

- [x] **Step 1: 生成维护状态页**

`维护状态.md` should include:

```markdown
# 维护状态

## 人读页面

## 系统底账

## 复核队列

## 本轮建议
```

- [x] **Step 2: audit report 增加 layer counts**

Report should include:

```json
{
  "layer": "human",
  "pages_scanned": 274,
  "layer_counts": {
    "human": 274,
    "transitional": 20,
    "ledger": 1288
  }
}
```

- [x] **Step 3: 验证**

Run:

```bash
python3 tools/linuxdo_surf.py knowledge-audit --config config/knowledge_sources.json --output output/linuxdo_surf/quality_audit_human_latest.json
jq '.layer, .pages_scanned, .layer_counts' output/linuxdo_surf/quality_audit_human_latest.json
```

Expected: 可以一眼看出人读页和机器底账各有多少。

---

## 执行顺序

推荐顺序：

```text
P0 Task 1  Watchlist 三态
P0 Task 2  Audit 分层
P0 Task 3  Metadata refresh
P0 Task 4  knowledge-prepare
P1 Task 5  frontier-add
P1 Task 6  context pack 截断
P1 Task 7  首页和导读收敛
P2 Task 8  review queue 生命周期
P2 Task 9  claim/issue 更新状态流
P2 Task 10 alias/canonical
P2 Task 11 vault 增长预算
```

不要在 P0 完成前继续全库大规模重写资源卡。P0 完成后，再按主题修旧内容：

```text
Agent CLI/IDE
workflow/skills
API/service
MCP/memory
models
```

每批 10-15 页，先生成 manifest，再回源补证据，再审本批页面。

---

## 最终验收

Run:

```bash
python3 -m unittest tests.test_linuxdo_knowledge
python3 tools/linuxdo_surf.py knowledge-prepare --config config/knowledge_sources.json --batch-size 20 --focus superpowers
python3 tools/linuxdo_surf.py knowledge-audit --config config/knowledge_sources.json --output output/linuxdo_surf/quality_audit_human_latest.json
python3 tools/linuxdo_surf.py knowledge-audit --config config/knowledge_sources.json --layer ledger --output output/linuxdo_surf/quality_audit_ledger_latest.json
rg -n "readings_all" output/linuxdo_surf/context_pack_latest.json output/linuxdo_surf/knowledge_task_latest.json
git diff --check
```

Expected:

```text
测试通过
knowledge-prepare 一键产出 feedback/context/task
context/task 不包含 readings_all
human audit 不扫描 _system 和 sessions
ledger audit 不跑人读文案规则
watchlist 只包含显式 watchlist:true
deprioritized/rejected 不进入普通刷新
git diff --check 无输出
```

---

## 自检

**Spec coverage:** 已覆盖使用体验、阅读体验、token 消耗、信息更新迭代、知识库维护五个方向。P0 对应当前最大风险，P1 对应日常使用顺手程度，P2 对应长期增长和证据更新。

**Placeholder scan:** 本计划没有 `TBD`、`TODO`、`implement later`、`类似上面` 这类占位步骤。每个代码任务都有目标文件、测试方向、命令和验收结果。

**Type consistency:** 计划中统一使用 `watchlist`、`status`、`feedback_preview`、`refresh_triggers`、`reply_count`、`read_reply_count`、`last_activity_at`、`read_last_activity_at`、`metadata_refreshed_at`。

