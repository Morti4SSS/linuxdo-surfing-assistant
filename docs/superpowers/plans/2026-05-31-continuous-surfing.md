# Continuous Surfing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first executable layer for continuous Linux.do surfing: queue construction, batch selection, discovery hints, `/goal` task generation, and session recording.

**Architecture:** Keep the existing single-file CLI shape in `tools/linuxdo_surf.py`. Add pure functions for queue building and selection so they are easy to test, then add two CLI commands: `goal-plan` to generate a resumable queue and `/goal` task, and `session` to save readings, update read state, and record why the current long-running pass stopped.

**Tech Stack:** Python standard library, argparse, JSON, unittest.

---

## File Structure

- Modify `tools/linuxdo_surf.py`
  - Add queue constants.
  - Add `build_frontier_queue`.
  - Add `select_next_batch`.
  - Add `extract_discovery_items`.
  - Add `build_goal_task`.
  - Add `build_session_record`.
  - Add CLI commands `goal-plan` and `session`.
- Modify `tests/test_linuxdo_surf.py`
  - Add unittest coverage for each new behavior.
- Create this implementation plan file.

## Task 1: Build Primary Surfing Queues

**Files:**
- Modify: `tools/linuxdo_surf.py`
- Modify: `tests/test_linuxdo_surf.py`

- [x] **Step 1: Write the failing test**

Add this test to `LinuxdoSurfTests`:

```python
def test_build_frontier_queue_splits_new_active_old_and_low_traffic_topics(self):
    topics = [
        {
            "id": 1,
            "title": "Codex 新工作流分享",
            "first_text": "codex workflow skill",
            "created_at": "2026-05-30T09:00:00",
            "last_posted_at": "2026-05-30T10:00:00",
            "views": 3000,
            "reply_count": 8,
        },
        {
            "id": 2,
            "title": "Claude Code 老经验帖更新",
            "first_text": "老帖里总结 workflow 踩坑",
            "created_at": "2026-03-01T09:00:00",
            "last_posted_at": "2026-05-30T10:00:00",
            "views": 5000,
            "reply_count": 80,
        },
        {
            "id": 3,
            "title": "冷门 MCP 配置求助",
            "first_text": "mcp 工具配置问题",
            "created_at": "2026-05-20T09:00:00",
            "last_posted_at": "2026-05-20T10:00:00",
            "views": 120,
            "reply_count": 2,
        },
    ]

    frontier = linuxdo_surf.build_frontier_queue(
        topics,
        mode="goldmine",
        query="",
        read_ids=set(),
        now="2026-05-31T00:00:00",
    )

    self.assertEqual([item["id"] for item in frontier["queues"]["new"]], [1])
    self.assertEqual([item["id"] for item in frontier["queues"]["active-old"]], [2])
    self.assertEqual([item["id"] for item in frontier["queues"]["low-traffic"]], [3])
```

- [x] **Step 2: Run the test to verify it fails**

Run:

```powershell
python -m unittest D:\workSpace\codex\information\linuxdo\tests\test_linuxdo_surf.py
```

Expected: ERROR because `build_frontier_queue` does not exist.

- [x] **Step 3: Implement minimal queue construction**

Add constants and functions:

```python
PRIMARY_QUEUE_NAMES = ("new", "active-old", "low-traffic")
DISCOVERY_QUEUE_NAMES = ("author-tracking", "comment-reference", "tool-lookup", "skill-workflow-evidence")
DEFAULT_QUEUE_QUOTAS = {"new": 0.4, "active-old": 0.4, "low-traffic": 0.2}


def build_frontier_queue(
    topics: list[dict[str, Any]],
    mode: str,
    query: str = "",
    skill_names: list[str] | None = None,
    read_ids: set[int] | None = None,
    now: str | datetime | None = None,
    max_candidates: int = 80,
) -> dict[str, Any]:
    mode = validate_mode(mode)
    read_ids = read_ids or set()
    current_time = _coerce_datetime(now) or datetime.now()
    queues = {name: [] for name in PRIMARY_QUEUE_NAMES}
    for topic in rank_topics(topics, mode, query, skill_names or [], read_ids, max_candidates):
        queue_name = _primary_queue_for_topic(topic, current_time)
        queues[queue_name].append(_frontier_item(topic, queue_name))
    return {
        "created_at": current_time.isoformat(timespec="seconds"),
        "mode": mode,
        "query": query,
        "queues": queues,
        "discovery_queues": {name: [] for name in DISCOVERY_QUEUE_NAMES},
        "quotas": dict(DEFAULT_QUEUE_QUOTAS),
    }
```

Helper behavior:

- `_primary_queue_for_topic` returns `active-old` when the topic is at least 30 days old and was active in the last 14 days.
- It returns `low-traffic` when `views <= 500` and `reply_count <= 10`.
- Otherwise it returns `new`.
- `_frontier_item` keeps `id`, `title`, `url`, `queue`, `surf_score`, `reason`, `created_at`, `last_posted_at`, `views`, and `reply_count`.

- [x] **Step 4: Run all tests**

Run:

```powershell
python -m unittest D:\workSpace\codex\information\linuxdo\tests\test_linuxdo_surf.py
```

Expected: all tests pass.

## Task 2: Select A Quota-Aware Next Batch

**Files:**
- Modify: `tools/linuxdo_surf.py`
- Modify: `tests/test_linuxdo_surf.py`

- [x] **Step 1: Write the failing test**

Add this test:

```python
def test_select_next_batch_respects_primary_queue_quotas_and_deduplicates(self):
    frontier = {
        "queues": {
            "new": [{"id": 1, "queue": "new"}, {"id": 2, "queue": "new"}],
            "active-old": [{"id": 3, "queue": "active-old"}, {"id": 4, "queue": "active-old"}],
            "low-traffic": [{"id": 5, "queue": "low-traffic"}, {"id": 3, "queue": "low-traffic"}],
        },
        "quotas": {"new": 0.4, "active-old": 0.4, "low-traffic": 0.2},
    }

    batch = linuxdo_surf.select_next_batch(frontier, max_topics=5)

    self.assertEqual([item["id"] for item in batch], [1, 2, 3, 4, 5])
    self.assertEqual(batch[-1]["queue"], "low-traffic")
```

- [x] **Step 2: Run the test to verify it fails**

Run:

```powershell
python -m unittest D:\workSpace\codex\information\linuxdo\tests\test_linuxdo_surf.py
```

Expected: ERROR because `select_next_batch` does not exist.

- [x] **Step 3: Implement quota-aware selection**

Add:

```python
def select_next_batch(frontier: dict[str, Any], max_topics: int) -> list[dict[str, Any]]:
    _validate_positive("max-topics", max_topics)
    quotas = frontier.get("quotas", DEFAULT_QUEUE_QUOTAS)
    queues = frontier.get("queues", {})
    selected = []
    seen_ids = set()
    for queue_name in PRIMARY_QUEUE_NAMES:
        quota_count = max(1, int(round(max_topics * float(quotas.get(queue_name, 0)))))
        for item in queues.get(queue_name, [])[:quota_count]:
            item_id = _safe_int(item.get("id"))
            if item_id is None or item_id in seen_ids:
                continue
            selected.append(item)
            seen_ids.add(item_id)
            if len(selected) >= max_topics:
                return selected
    for queue_name in PRIMARY_QUEUE_NAMES:
        for item in queues.get(queue_name, []):
            item_id = _safe_int(item.get("id"))
            if item_id is None or item_id in seen_ids:
                continue
            selected.append(item)
            seen_ids.add(item_id)
            if len(selected) >= max_topics:
                return selected
    return selected
```

- [x] **Step 4: Run all tests**

Run:

```powershell
python -m unittest D:\workSpace\codex\information\linuxdo\tests\test_linuxdo_surf.py
```

Expected: all tests pass.

## Task 3: Extract Discovery Hints From Readings

**Files:**
- Modify: `tools/linuxdo_surf.py`
- Modify: `tests/test_linuxdo_surf.py`

- [x] **Step 1: Write the failing test**

Add this test:

```python
def test_extract_discovery_items_builds_author_reference_and_tool_queues(self):
    readings = [
        {
            "id": 10,
            "url": "https://linux.do/t/topic/10",
            "title": "Codex workflow",
            "author": "alice",
            "summary": "推荐了 workflow-kit 和 skill-router。",
            "tools": ["workflow-kit", "go"],
            "high_value_replies": [
                {
                    "id": 99,
                    "author": "bob",
                    "text": "之前有个帖子 https://linux.do/t/topic/20 讨论 skill-router 的风险。",
                }
            ],
        }
    ]

    discovery = linuxdo_surf.extract_discovery_items(readings)

    self.assertEqual(discovery["author-tracking"][0]["username"], "alice")
    self.assertEqual(discovery["comment-reference"][0]["target_url"], "https://linux.do/t/topic/20")
    self.assertEqual([item["name"] for item in discovery["tool-lookup"]], ["workflow-kit", "skill-router"])
```

- [x] **Step 2: Run the test to verify it fails**

Run:

```powershell
python -m unittest D:\workSpace\codex\information\linuxdo\tests\test_linuxdo_surf.py
```

Expected: ERROR because `extract_discovery_items` does not exist.

- [x] **Step 3: Implement discovery extraction**

Add:

```python
def extract_discovery_items(readings: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    discovery = {name: [] for name in DISCOVERY_QUEUE_NAMES}
    for reading in readings:
        _add_author_discovery(discovery, reading)
        _add_tool_discovery(discovery, reading)
        _add_reference_discovery(discovery, reading)
    return {name: _dedupe_discovery_items(items) for name, items in discovery.items()}
```

Helper rules:

- Author tracking stores `username`, `profile_url`, `source_topic_ids`, `reason`, `score`, `last_seen_at`, `cooldown_until`.
- Comment reference extracts `https://linux.do/t/topic/<id>` URLs from high-value reply text.
- Tool lookup uses explicit `tools` values and capitalized or hyphenated names in summaries, but ignores names shorter than 3 characters such as `go`.
- Tool lookup stores `name`, `aliases`, `source_topic_ids`, `source_urls`, `category`, `evidence_count`, `positive_count`, `negative_count`, `score`.

- [x] **Step 4: Run all tests**

Run:

```powershell
python -m unittest D:\workSpace\codex\information\linuxdo\tests\test_linuxdo_surf.py
```

Expected: all tests pass.

## Task 4: Generate `/goal` Task Files

**Files:**
- Modify: `tools/linuxdo_surf.py`
- Modify: `tests/test_linuxdo_surf.py`

- [x] **Step 1: Write the failing test**

Add this test:

```python
def test_cli_goal_plan_writes_frontier_queue_and_goal_task(self):
    with TemporaryDirectoryPath() as tmp_path:
        topics_path = tmp_path / "topics.json"
        topics_path.write_text(
            json.dumps({"topics": [{"id": 1, "title": "Codex workflow", "first_text": "workflow", "views": 10}]}),
            encoding="utf-8",
        )
        out_dir = tmp_path / "out"
        state_path = tmp_path / "state.json"
        queue_path = tmp_path / "frontier.json"

        exit_code = linuxdo_surf.main(
            [
                "goal-plan",
                "--mode",
                "goldmine",
                "--topics",
                str(topics_path),
                "--output",
                str(out_dir),
                "--state",
                str(state_path),
                "--queue",
                str(queue_path),
                "--max-topics",
                "1",
            ]
        )

        frontier = json.loads(queue_path.read_text(encoding="utf-8"))
        task = json.loads((out_dir / "goal_task_goldmine.json").read_text(encoding="utf-8"))

    self.assertEqual(exit_code, 0)
    self.assertEqual(task["control_channel"], "mac-goal")
    self.assertEqual(task["frontier_queue"], str(queue_path))
    self.assertEqual(task["next_batch"][0]["id"], 1)
    self.assertIn("low-traffic", frontier["queues"])
```

- [x] **Step 2: Run the test to verify it fails**

Run:

```powershell
python -m unittest D:\workSpace\codex\information\linuxdo\tests\test_linuxdo_surf.py
```

Expected: argparse rejects unknown command `goal-plan`.

- [x] **Step 3: Implement `goal-plan`**

Add `build_goal_task`:

```python
def build_goal_task(
    mode: str,
    query: str,
    frontier_path: Path,
    state_path: Path,
    output_path: Path,
    next_batch: list[dict[str, Any]],
    max_topics: int,
    max_replies: int,
) -> dict[str, Any]:
    mode = validate_mode(mode)
    return {
        "mode": mode,
        "control_channel": "mac-goal",
        "query": query,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "frontier_queue": str(frontier_path),
        "state": str(state_path),
        "output": str(output_path),
        "budget": {"max_topics": max_topics, "max_replies_per_topic": max_replies},
        "stop_conditions": [
            "next_batch 为空",
            "达到本轮深读预算",
            "连续批次没有发现高价值候选",
        ],
        "instructions": _goal_instructions(mode),
        "next_batch": next_batch,
    }
```

Add `run_goal_plan` and parser command:

```python
goal_plan = subparsers.add_parser("goal-plan", help="生成 Mac /goal 持续冲浪任务包。")
goal_plan.add_argument("--mode", required=True, choices=sorted(MODES))
goal_plan.add_argument("--query", default="")
goal_plan.add_argument("--skills", nargs="*", default=[])
goal_plan.add_argument("--topics", type=Path, default=Path("output/linuxdo_skill_research/topic_details_top220.json"))
goal_plan.add_argument("--output", type=Path, default=Path("output/linuxdo_surf"))
goal_plan.add_argument("--state", type=Path, default=Path("state/linuxdo_surf_state.json"))
goal_plan.add_argument("--queue", type=Path, default=Path("state/linuxdo_frontier_queue.json"))
goal_plan.add_argument("--max-candidates", type=int, default=80)
goal_plan.add_argument("--max-topics", type=int, default=12)
goal_plan.add_argument("--max-replies", type=int, default=8)
goal_plan.set_defaults(func=run_goal_plan)
```

- [x] **Step 4: Run all tests**

Run:

```powershell
python -m unittest D:\workSpace\codex\information\linuxdo\tests\test_linuxdo_surf.py
```

Expected: all tests pass.

## Task 5: Record Session Results And Discovery Queues

**Files:**
- Modify: `tools/linuxdo_surf.py`
- Modify: `tests/test_linuxdo_surf.py`

- [x] **Step 1: Write the failing test**

Add this test:

```python
def test_cli_session_writes_session_record_and_updates_state(self):
    with TemporaryDirectoryPath() as tmp_path:
        task_path = tmp_path / "goal_task_goldmine.json"
        task_path.write_text(
            json.dumps({"mode": "goldmine", "query": "", "next_batch": [{"id": 10}]}),
            encoding="utf-8",
        )
        readings_path = tmp_path / "readings.json"
        readings_path.write_text(
            json.dumps({"readings": [{"id": 10, "title": "工具讨论", "summary": "推荐 workflow-kit", "tools": ["workflow-kit"]}]}),
            encoding="utf-8",
        )
        out_dir = tmp_path / "out"
        state_path = tmp_path / "state.json"

        exit_code = linuxdo_surf.main(
            [
                "session",
                "--task",
                str(task_path),
                "--readings",
                str(readings_path),
                "--output",
                str(out_dir),
                "--state",
                str(state_path),
                "--stop-reason",
                "达到本轮深读预算",
            ]
        )

        session_files = list(out_dir.glob("session_goldmine_*.json"))
        session = json.loads(session_files[0].read_text(encoding="utf-8"))
        state = json.loads(state_path.read_text(encoding="utf-8"))

    self.assertEqual(exit_code, 0)
    self.assertEqual(session["stop_reason"], "达到本轮深读预算")
    self.assertEqual(session["read_topic_ids"], [10])
    self.assertEqual(session["discovery_queues"]["tool-lookup"][0]["name"], "workflow-kit")
    self.assertEqual(state["read_topic_ids"], [10])
```

- [x] **Step 2: Run the test to verify it fails**

Run:

```powershell
python -m unittest D:\workSpace\codex\information\linuxdo\tests\test_linuxdo_surf.py
```

Expected: argparse rejects unknown command `session`.

- [x] **Step 3: Implement session recording**

Add:

```python
def build_session_record(task: dict[str, Any], readings: list[dict[str, Any]], stop_reason: str) -> dict[str, Any]:
    mode = validate_mode(str(task.get("mode", "")))
    result = build_mode_result(task, readings)
    return {
        "mode": mode,
        "query": task.get("query", ""),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "stop_reason": stop_reason,
        "read_topic_ids": result["read_topic_ids"],
        "items": result["items"],
        "mode_summary": result["mode_summary"],
        "discovery_queues": extract_discovery_items(readings),
    }
```

Add `run_session`, output filename `session_<mode>_<YYYYmmddHHMMSSffffff>.json` with collision suffix fallback, and update `read_topic_ids` in state.

- [x] **Step 4: Run all tests**

Run:

```powershell
python -m unittest D:\workSpace\codex\information\linuxdo\tests\test_linuxdo_surf.py
```

Expected: all tests pass.

## Task 6: Verify, Commit, And Sync

**Files:**
- Modify: `tools/linuxdo_surf.py`
- Modify: `tests/test_linuxdo_surf.py`
- Create: `docs/superpowers/plans/2026-05-31-continuous-surfing.md`

- [x] **Step 1: Run verification**

Run:

```powershell
python -m unittest D:\workSpace\codex\information\linuxdo\tests\test_linuxdo_surf.py
git status --short
```

Expected: tests pass; only intended files are changed.

- [ ] **Step 2: Commit**

Run:

```powershell
git add tools/linuxdo_surf.py tests/test_linuxdo_surf.py docs/superpowers/plans/2026-05-31-continuous-surfing.md
git commit -m "feat: add continuous surfing queues"
```

Expected: commit succeeds.

- [ ] **Step 3: Sync remote**

Run:

```powershell
git push origin master
```

If `github.com:443` fails but `api.github.com:443` works, use GitHub API or GitHub MCP fallback and report that remote commit history differs from local Git SHA.

---

Self-review:

- Spec coverage: includes primary queues, active-old historical context, quota selection, `/goal` task generation, session records, author tracking, comment reference expansion, and tool name reverse lookup.
- Placeholder scan: no `TBD`, `TODO`, or vague implementation placeholders remain.
- Type consistency: uses `build_frontier_queue`, `select_next_batch`, `extract_discovery_items`, `build_goal_task`, `build_session_record`, `goal-plan`, and `session` consistently.
