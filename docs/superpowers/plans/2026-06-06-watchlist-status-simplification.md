# Watchlist Status Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Simplify user-facing priority controls to three states while making Obsidian edits reliably affect the next Linux.do surfing run.

**Architecture:** Keep the human interface small: `watchlist` means “track this”, and `status` uses only `watching`, `deprioritized`, or `rejected` for manual priority. Expand feedback sync so all main human-facing pages are indexed. Adjust planning so `watchlist: false` and negative statuses suppress work instead of accidentally triggering refresh because a file changed.

**Tech Stack:** Python standard library, existing `tools/linuxdo_knowledge/*` modules, `unittest`, Obsidian Markdown frontmatter, generated guide pages.

---

## Human Rule To Preserve

Use this as the product rule throughout the implementation:

```text
想追：watchlist: true + status: watching
暂时不看：watchlist: false + status: deprioritized
明确不要：watchlist: false + status: rejected
```

Other fields such as `evidence_status` and `staleness_risk` are agent-maintained evidence fields, not normal manual controls.

## File Map

- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/feedback.py`
  - Expand feedback scanning directories.
  - Normalize manual priority signals.
  - Store `watchlist` in `user_feedback` as well as `resource_index`.

- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/context_pack.py`
  - Make `watchlist` section mean explicit `watchlist: true`, not `status: watching`.
  - Add or keep separate feedback/status signals so `watching` remains visible but not confused with watchlist.

- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/strategy.py`
  - Make `deprioritized` and `rejected` suppress refresh.
  - Avoid treating a changed `watchlist: false` file as a positive refresh signal.
  - Use resource watchlist/status to influence related topics when `related_resources` connects them.

- Modify: `/Users/mortisss/Documents/linuxdo/tools/linuxdo_knowledge/second_pass.py`
  - Simplify generated guide and Watchlist pages so the user sees only the three-state rule.

- Modify: `/Users/mortisss/Documents/linuxdo/tests/test_linuxdo_knowledge.py`
  - Add regression tests for sync directories, context pack semantics, planning suppression, and guide text.

---

### Task 1: Expand Feedback Sync Coverage

**Files:**
- Modify: `tools/linuxdo_knowledge/feedback.py`
- Modify: `tests/test_linuxdo_knowledge.py`

- [ ] **Step 1: Add failing test for main page directories**

Add a test under `FeedbackSyncTests`:

```python
    def test_sync_feedback_scans_all_main_human_page_directories(self):
        from tools.linuxdo_knowledge.feedback import sync_feedback
        from tools.linuxdo_knowledge.state import load_hot_indexes

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            pages = {
                "10_Catalog/services/CPA.md": "resource:cpa",
                "10_Catalog/collections/API-中转.md": "resource:api-relay",
                "20_Knowledge/concepts/memory.md": "resource:memory",
                "20_Knowledge/components/grill-me.md": "resource:grill-me",
            }
            for relative_path, item_id in pages.items():
                path = config.obsidian_vault_path / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    f"---\nid: {item_id}\ntype: resource\nstatus: watching\nwatchlist: true\n---\n"
                    f"# {path.stem}\n\n## 我的反馈\n\n想继续追。\n",
                    encoding="utf-8",
                )

            result = sync_feedback(config, synced_at="2026-06-06T12:00:00+08:00")
            indexes = load_hot_indexes(config)

        self.assertEqual(result["changed_files"], 4)
        for item_id in pages.values():
            self.assertTrue(indexes["resource_index"]["resources"][item_id]["watchlist"])
```

- [ ] **Step 2: Expand scan directories**

In `feedback.py`, change `FEEDBACK_SCAN_DIRECTORIES` to include:

```python
FEEDBACK_SCAN_DIRECTORIES = (
    "10_Catalog/resources",
    "10_Catalog/services",
    "10_Catalog/collections",
    "10_Catalog/candidates",
    "10_Catalog/comparisons",
    "10_Catalog/workflows",
    "20_Knowledge/concepts",
    "20_Knowledge/components",
    "20_Knowledge/claims",
    "30_Feedback",
    "90_Inbox/review-queue",
)
```

- [ ] **Step 3: Run targeted test**

Run:

```bash
python3 -m unittest tests.test_linuxdo_knowledge.FeedbackSyncTests.test_sync_feedback_scans_all_main_human_page_directories
```

Expected: PASS.

**给子线程的中文提示词：**

```text
你负责“feedback-sync 扫描范围补全”。请只改 tools/linuxdo_knowledge/feedback.py 和 tests/test_linuxdo_knowledge.py。目标是让 services、collections、concepts、components 里的 watchlist/status/我的反馈 也能被下次同步读到。不要改 Obsidian vault 内容。完成后运行指定单测并汇报。
```

---

### Task 2: Make User Feedback Carry Watchlist and Status Clearly

**Files:**
- Modify: `tools/linuxdo_knowledge/feedback.py`
- Modify: `tests/test_linuxdo_knowledge.py`

- [ ] **Step 1: Add failing test for feedback payload**

Add under `FeedbackSyncTests`:

```python
    def test_sync_feedback_records_watchlist_and_negative_status_in_user_feedback(self):
        from tools.linuxdo_knowledge.feedback import sync_feedback
        from tools.linuxdo_knowledge.state import load_hot_indexes

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            path = config.obsidian_vault_path / "10_Catalog" / "resources" / "Tool.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "---\nid: resource:tool\ntype: resource\nstatus: deprioritized\nwatchlist: false\n---\n"
                "# Tool\n\n## 我的反馈\n\n暂时不看，但不拉黑。\n",
                encoding="utf-8",
            )

            sync_feedback(config, synced_at="2026-06-06T12:00:00+08:00")
            indexes = load_hot_indexes(config)
            feedback_item = indexes["user_feedback"]["items"][0]
            resource_item = indexes["resource_index"]["resources"]["resource:tool"]

        self.assertEqual(feedback_item["status"], "deprioritized")
        self.assertFalse(feedback_item["watchlist"])
        self.assertEqual(resource_item["status"], "deprioritized")
        self.assertFalse(resource_item["watchlist"])
```

- [ ] **Step 2: Include watchlist in user feedback payload**

In `_record_feedback()`, add:

```python
if "watchlist" in parsed:
    payload["watchlist"] = _parse_bool(parsed.get("watchlist"))
```

- [ ] **Step 3: Run targeted test**

Run:

```bash
python3 -m unittest tests.test_linuxdo_knowledge.FeedbackSyncTests.test_sync_feedback_records_watchlist_and_negative_status_in_user_feedback
```

Expected: PASS.

**给子线程的中文提示词：**

```text
你负责“反馈 payload 语义清晰化”。请只改 feedback.py 和 tests/test_linuxdo_knowledge.py。目标是 user_feedback 里也保存 watchlist true/false，status: deprioritized/rejected 也清楚同步，方便后续策略区分“暂时不看”和“明确不要”。完成后运行指定单测。
```

---

### Task 3: Separate Watchlist From Watching in Context Pack

**Files:**
- Modify: `tools/linuxdo_knowledge/context_pack.py`
- Modify: `tests/test_linuxdo_knowledge.py`

- [ ] **Step 1: Add failing test**

Add under `KnowledgeQualityRulesTests` or an existing context pack test class:

```python
    def test_context_pack_watchlist_requires_explicit_true(self):
        from tools.linuxdo_knowledge.context_pack import build_context_pack
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, save_hot_index

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            ensure_knowledge_state(config)
            save_hot_index(
                config,
                "resource_index",
                {
                    "resources": {
                        "resource:watch": {"id": "resource:watch", "title": "Watch", "status": "candidate", "watchlist": True},
                        "resource:observe": {"id": "resource:observe", "title": "Observe", "status": "watching", "watchlist": False},
                    }
                },
            )

            pack = build_context_pack(config, limit=20)

        self.assertEqual([item["id"] for item in pack["watchlist"]], ["resource:watch"])
```

- [ ] **Step 2: Change context pack watchlist logic**

In `context_pack.py`, replace:

```python
watchlist = [item for item in resources if item.get("watchlist") or item.get("status") in {"watching", "adopted"}]
```

with:

```python
watchlist = [item for item in resources if item.get("watchlist") is True]
```

If you want to keep `watching` visible, add a separate key:

```python
watching = [item for item in resources if item.get("status") == "watching" and item.get("watchlist") is not True]
```

and include `"watching": _filter_limit(watching, focus, limit)`.

- [ ] **Step 3: Run targeted test**

Run:

```bash
python3 -m unittest tests.test_linuxdo_knowledge.KnowledgeQualityRulesTests.test_context_pack_watchlist_requires_explicit_true
```

Expected: PASS.

**给子线程的中文提示词：**

```text
你负责“context pack 语义拆分”。请只改 context_pack.py 和 tests/test_linuxdo_knowledge.py。目标是 watchlist 只表示显式 watchlist: true，不再把 status: watching 自动混进去；如果需要观察态，另放 watching 字段。完成后运行指定单测。
```

---

### Task 4: Suppress Deprioritized and Rejected Signals in Planning

**Files:**
- Modify: `tools/linuxdo_knowledge/strategy.py`
- Modify: `tests/test_linuxdo_knowledge.py`

- [ ] **Step 1: Add failing test for changed negative feedback**

Add under `ReadingStrategyTests`:

```python
    def test_build_knowledge_task_does_not_refresh_deprioritized_resource_feedback(self):
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, save_hot_index
        from tools.linuxdo_knowledge.strategy import build_knowledge_task

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            ensure_knowledge_state(config)
            save_hot_index(
                config,
                "topic_update_state",
                {
                    "topics": {
                        "42": {
                            "topic_id": 42,
                            "title": "Tool discussion",
                            "url": "https://linux.do/t/topic/42",
                            "related_resources": ["tool"],
                            "last_read_at": "2026-06-05T12:00:00+08:00",
                            "reply_count": 10,
                            "read_reply_count": 10,
                        }
                    }
                },
            )
            save_hot_index(
                config,
                "user_feedback",
                {
                    "items": [
                        {
                            "id": "resource:tool",
                            "status": "deprioritized",
                            "watchlist": False,
                            "synced_at": "2026-06-06T12:00:00+08:00",
                        }
                    ]
                },
            )

            task = build_knowledge_task(config, batch_size=20, created_at="2026-06-06T12:30:00+08:00")

        self.assertEqual(task["items"], [])
```

- [ ] **Step 2: Add failing test for positive watchlist feedback**

Add:

```python
    def test_build_knowledge_task_refreshes_related_topic_for_watchlisted_resource(self):
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, save_hot_index
        from tools.linuxdo_knowledge.strategy import build_knowledge_task

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            ensure_knowledge_state(config)
            save_hot_index(
                config,
                "topic_update_state",
                {
                    "topics": {
                        "42": {
                            "topic_id": 42,
                            "title": "Tool discussion",
                            "url": "https://linux.do/t/topic/42",
                            "related_resources": ["tool"],
                            "last_read_at": "2026-06-05T12:00:00+08:00",
                            "reply_count": 12,
                            "read_reply_count": 10,
                        }
                    }
                },
            )
            save_hot_index(
                config,
                "user_feedback",
                {
                    "items": [
                        {
                            "id": "resource:tool",
                            "status": "watching",
                            "watchlist": True,
                            "synced_at": "2026-06-06T12:00:00+08:00",
                        }
                    ]
                },
            )

            task = build_knowledge_task(config, batch_size=20, created_at="2026-06-06T12:30:00+08:00")

        self.assertEqual(task["items"][0]["topic_id"], 42)
        self.assertIn("watchlist", task["items"][0]["refresh_triggers"])
```

- [ ] **Step 3: Update feedback signal model**

In `strategy.py`, replace `_feedback_signals()` return value from `dict[str, str]` to a payload dict:

```python
signals[item_id] = {
    "synced_at": synced_at,
    "status": status,
    "watchlist": watchlist,
    "negative": status in {"deprioritized", "rejected"} or watchlist is False,
}
```

Then update `_feedback_references_topic()` to return only positive feedback signals. Negative feedback should not trigger refresh.

- [ ] **Step 4: Suppress negative statuses**

Ensure `_is_suppressed_topic()` includes:

```python
return _str_or_empty(topic.get("status")).lower() in {"deprioritized", "rejected", "archived"}
```

When merging topic and related feedback, do not include candidates whose matching feedback signal is negative.

- [ ] **Step 5: Run strategy tests**

Run:

```bash
python3 -m unittest tests.test_linuxdo_knowledge.ReadingStrategyTests
```

Expected: PASS.

**给子线程的中文提示词：**

```text
你负责“计划优先级三态逻辑”。请只改 strategy.py 和 tests/test_linuxdo_knowledge.py。目标是：watchlist true 会帮助相关 topic 进入刷新；deprioritized/rejected 或 watchlist false 不会因为文件刚改过就触发刷新。完成后运行 ReadingStrategyTests。
```

---

### Task 5: Simplify Generated Guidance Text

**Files:**
- Modify: `tools/linuxdo_knowledge/second_pass.py`
- Modify: `tests/test_linuxdo_knowledge.py`

- [ ] **Step 1: Add failing guide text test**

Extend the existing guide/watchlist tests so generated pages contain:

```python
        self.assertIn("想追：`watchlist: true` + `status: watching`", watchlist_text)
        self.assertIn("暂时不看：`watchlist: false` + `status: deprioritized`", watchlist_text)
        self.assertIn("明确不要：`watchlist: false` + `status: rejected`", watchlist_text)
        self.assertIn("其他字段由 agent 维护", watchlist_text)
        self.assertNotIn("active", watchlist_text)
        self.assertNotIn("disputed", watchlist_text)
        self.assertNotIn("adopted", watchlist_text)
```

- [ ] **Step 2: Update generated `怎么读这个知识库` text**

In `second_pass.py`, rewrite the field/status explanation to say:

```text
人手动只管三种：
- 想追：`watchlist: true` + `status: watching`
- 暂时不看：`watchlist: false` + `status: deprioritized`
- 明确不要：`watchlist: false` + `status: rejected`
其他字段由 agent 维护，不需要日常手改。
```

- [ ] **Step 3: Update `Watchlist-使用规则` text**

Use the same three-state rule and explain:

```text
`deprioritized` 是“暂时不看，但不拉黑”。
```

- [ ] **Step 4: Run guide tests**

Run:

```bash
python3 -m unittest tests.test_linuxdo_knowledge.LegacyMigrationTests.test_knowledge_organize_existing_writes_guides_comparisons_and_review_queue
```

Expected: PASS.

**给子线程的中文提示词：**

```text
你负责“导读文案简化”。请只改 second_pass.py 和 tests/test_linuxdo_knowledge.py。目标是让导读只告诉用户三态：想追、暂时不看、明确不要；其他 evidence/staleness 字段归 agent 维护。不要改 Obsidian vault 内容，完成后运行指定 guide 测试。
```

---

### Task 6: Final Verification

**Files:**
- No planned edits.

- [ ] **Step 1: Run all tests**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

Expected: PASS.

- [ ] **Step 2: Run diff check**

Run:

```bash
git diff --check HEAD
```

Expected: no output.

- [ ] **Step 3: Run sync, context pack, and plan smoke**

Run:

```bash
python3 tools/linuxdo_surf.py feedback-sync --config config/knowledge_sources.json --output output/linuxdo_surf/feedback_sync_latest.json
python3 tools/linuxdo_surf.py knowledge-context-pack --config config/knowledge_sources.json --focus superpowers --output output/linuxdo_surf/context_pack_latest.json
python3 tools/linuxdo_surf.py knowledge-plan --config config/knowledge_sources.json --batch-size 20 --output output/linuxdo_surf/knowledge_task_latest.json
```

Expected:

- all commands exit 0;
- `context_pack_latest.json` does not include `readings_all`;
- `knowledge_task_latest.json` has `"history_policy": "load_hot_indexes_only"`;
- `watchlist` in context pack contains only explicit `watchlist: true` items.

**给子线程的中文提示词：**

```text
你负责最终验证，不做代码修改。请运行完整测试、git diff --check、feedback-sync、knowledge-context-pack、knowledge-plan，并确认 context pack 不包含 readings_all，knowledge-plan 仍是 load_hot_indexes_only，watchlist 只包含显式 watchlist true 项。把失败项按必须修复/可排队/需要用户确认分类。
```

---

## Execution Order

Recommended sequence:

1. Task 1 and Task 2 can run together because they both touch `feedback.py` but in small adjacent areas; if avoiding conflicts, run Task 1 first.
2. Task 3 can run independently.
3. Task 4 should run after Task 2 because it depends on `user_feedback.watchlist`.
4. Task 5 can run independently.
5. Task 6 runs last.

## Acceptance Criteria

- User can edit `watchlist` in resources, services, collections, workflows, concepts, and components, and `feedback-sync` will see it.
- Human guidance only presents three manual states.
- `context_pack.watchlist` means explicit watchlist, not generic observation.
- `deprioritized` and `rejected` do not create refresh tasks merely because the page changed.
- The next surfing run still starts with `feedback-sync`, then `knowledge-context-pack` / `knowledge-plan`.
