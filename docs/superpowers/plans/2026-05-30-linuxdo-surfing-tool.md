# Linux.do 冲浪工具 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一个 Windows 优先的 Linux.do 任务型冲浪 CLI，支持四种模式、阅读任务包、去重状态和 skill 管理证据导出。

**Architecture:** 第一版不把本地脚本伪装成浏览器爬虫。Codex 内置浏览器负责登录态阅读，CLI 负责生成阅读任务、处理已有 topic 数据、记录已读状态、提炼结构化结果并导出给 skill 管理项目。核心逻辑集中在一个 Python 模块中，后续稳定后再拆分。

**Tech Stack:** Python 3 标准库、PowerShell 既有 CDP 脚本、JSON/JSONL 文件存储、pytest 测试。

---

## 文件结构

- Create: `tools/linuxdo_surf.py`
  - 单文件 CLI 和核心逻辑。
  - 负责四种模式、topic 加载、候选排序、状态读写、阅读任务包生成、结果提炼、skill 证据导出。
- Create: `tests/test_linuxdo_surf.py`
  - 覆盖核心纯函数和 CLI 行为。
- Create: `state/linuxdo_surf_state.json`
  - 运行时生成，不提交为固定内容。保存已读 topic 和已同步 skill 证据状态。
- Create: `output/linuxdo_surf/*.json`
  - 运行时生成，不提交为固定内容。保存阅读任务包、模式结果、skill 证据包。
- Existing reference: `docs/linuxdo-surfing-tool-design.md`
  - 需求来源。
- Existing reference: `tools/collect_linuxdo_research.ps1`
  - 后续仍用于通过已登录浏览器收集候选 topic。
- Existing reference: `tools/fetch_linuxdo_topic_details.ps1`
  - 后续仍用于通过已登录浏览器读取 topic 详情。

## 任务拆分

### Task 1: 核心模型、模式校验和 topic 排序

**Files:**
- Create: `tests/test_linuxdo_surf.py`
- Create: `tools/linuxdo_surf.py`

- [ ] **Step 1: 写失败测试**

```python
import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "linuxdo_surf.py"
spec = importlib.util.spec_from_file_location("linuxdo_surf", MODULE_PATH)
linuxdo_surf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(linuxdo_surf)


def test_validate_mode_accepts_four_modes():
    assert linuxdo_surf.validate_mode("research") == "research"
    assert linuxdo_surf.validate_mode("goldmine") == "goldmine"
    assert linuxdo_surf.validate_mode("skill-feedback") == "skill-feedback"
    assert linuxdo_surf.validate_mode("discover") == "discover"


def test_validate_mode_rejects_unknown_mode():
    try:
        linuxdo_surf.validate_mode("daily")
    except ValueError as error:
        assert "未知模式" in str(error)
    else:
        raise AssertionError("validate_mode should reject unsupported modes")


def test_rank_topics_prefers_query_matches_and_skips_read_ids():
    topics = [
        {"id": 1, "title": "普通闲聊", "first_text": "没有重点", "like_count": 50, "reply_count": 20, "views": 1000},
        {"id": 2, "title": "Codex 长任务工作流经验", "first_text": "讨论 codex workflow skill", "like_count": 5, "reply_count": 2, "views": 100},
        {"id": 3, "title": "Codex skill 路由", "first_text": "skill 管理和工作流", "like_count": 1, "reply_count": 1, "views": 50},
    ]

    ranked = linuxdo_surf.rank_topics(topics, mode="research", query="Codex 工作流", read_ids={3}, limit=5)

    assert [item["id"] for item in ranked] == [2, 1]
    assert ranked[0]["surf_score"] > ranked[1]["surf_score"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest D:\workSpace\codex\information\linuxdo\tests\test_linuxdo_surf.py -q`

Expected: FAIL，因为 `tools/linuxdo_surf.py` 还不存在。

- [ ] **Step 3: 写最小实现**

在 `tools/linuxdo_surf.py` 中实现：

```python
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


MODES = {"research", "goldmine", "skill-feedback", "discover"}
DEFAULT_KEYWORDS = {
    "goldmine": ["ai coding", "codex", "claude code", "skill", "mcp", "workflow", "工作流", "插件", "开源", "经验"],
    "discover": ["skill", "workflow", "harness", "mcp", "cli", "插件", "工具", "开源", "推荐"],
}


def validate_mode(mode: str) -> str:
    normalized = mode.strip().lower()
    if normalized not in MODES:
        raise ValueError(f"未知模式：{mode}")
    return normalized


def rank_topics(
    topics: list[dict[str, Any]],
    mode: str,
    query: str = "",
    skill_names: list[str] | None = None,
    read_ids: set[int] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    validate_mode(mode)
    read_ids = read_ids or set()
    keywords = _keywords_for(mode, query, skill_names or [])
    ranked = []
    for topic in topics:
        topic_id = int(topic.get("id", 0) or 0)
        if topic_id in read_ids:
            continue
        score = _topic_score(topic, keywords)
        ranked.append({**topic, "surf_score": round(score, 2)})
    ranked.sort(key=lambda item: (-item["surf_score"], str(item.get("title", ""))))
    return ranked[:limit]


def _keywords_for(mode: str, query: str, skill_names: list[str]) -> list[str]:
    words: list[str] = []
    if query:
        words.extend(_split_terms(query))
    if mode in DEFAULT_KEYWORDS:
        words.extend(DEFAULT_KEYWORDS[mode])
    if mode == "skill-feedback":
        words.extend(skill_names)
        words.extend(["skill", "skills", "推荐", "吐槽", "对比", "替代"])
    return _unique([word for word in words if word])


def _topic_score(topic: dict[str, Any], keywords: list[str]) -> float:
    title = str(topic.get("title", ""))
    text = " ".join(
        [
            title,
            str(topic.get("first_text", "")),
            " ".join(str(tag) for tag in topic.get("tags", []) or []),
        ]
    ).lower()
    score = 0.0
    for keyword in keywords:
        key = keyword.lower()
        if not key:
            continue
        if key in title.lower():
            score += 10
        elif key in text:
            score += 4
    score += min(float(topic.get("like_count", 0) or 0), 50) / 5
    score += min(float(topic.get("reply_count", 0) or 0), 100) / 10
    score += min(float(topic.get("views", 0) or 0), 10000) / 2000
    return score


def _split_terms(text: str) -> list[str]:
    return [part for part in re.split(r"[\s,，、/]+", text.strip()) if part]


def _unique(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        key = value.lower()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest D:\workSpace\codex\information\linuxdo\tests\test_linuxdo_surf.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

如果目录已是 Git 仓库：

```bash
git add tools/linuxdo_surf.py tests/test_linuxdo_surf.py
git commit -m "feat: add linuxdo surf topic ranking"
```

如果不是 Git 仓库，跳过提交并在最终说明中注明。

### Task 2: 状态存储和阅读任务包生成

**Files:**
- Modify: `tests/test_linuxdo_surf.py`
- Modify: `tools/linuxdo_surf.py`

- [ ] **Step 1: 写失败测试**

追加测试：

```python
def test_load_state_returns_default_when_missing(tmp_path):
    state = linuxdo_surf.load_state(tmp_path / "missing.json")

    assert state == {"read_topic_ids": [], "synced_skill_names": []}


def test_save_state_normalizes_topic_ids_and_skill_names(tmp_path):
    path = tmp_path / "state.json"

    linuxdo_surf.save_state(path, {"read_topic_ids": [3, "2", 3], "synced_skill_names": ["A", "a", "B"]})

    saved = linuxdo_surf.load_state(path)
    assert saved["read_topic_ids"] == [2, 3]
    assert saved["synced_skill_names"] == ["A", "B"]


def test_build_browser_task_contains_mode_budget_and_candidates():
    candidates = [
        {"id": 2, "title": "Codex 长任务工作流经验", "url": "https://linux.do/t/topic/2", "surf_score": 21.5}
    ]

    task = linuxdo_surf.build_browser_task(
        mode="research",
        query="Codex 工作流",
        candidates=candidates,
        skill_names=[],
        max_topics=3,
        max_replies=5,
    )

    assert task["mode"] == "research"
    assert task["query"] == "Codex 工作流"
    assert task["budget"] == {"max_topics": 3, "max_replies_per_topic": 5}
    assert task["candidates"][0]["id"] == 2
    assert "Codex 内置浏览器" in task["instructions"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest D:\workSpace\codex\information\linuxdo\tests\test_linuxdo_surf.py -q`

Expected: FAIL，因为状态和任务包函数不存在。

- [ ] **Step 3: 写最小实现**

在 `tools/linuxdo_surf.py` 中追加：

```python
DEFAULT_STATE = {"read_topic_ids": [], "synced_skill_names": []}


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return dict(DEFAULT_STATE)
    data = json.loads(path.read_text(encoding="utf-8"))
    return _normalize_state(data)


def save_state(path: Path, state: dict[str, Any]) -> None:
    normalized = _normalize_state(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")


def build_browser_task(
    mode: str,
    query: str,
    candidates: list[dict[str, Any]],
    skill_names: list[str],
    max_topics: int,
    max_replies: int,
) -> dict[str, Any]:
    mode = validate_mode(mode)
    return {
        "mode": mode,
        "query": query,
        "skill_names": skill_names,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "budget": {"max_topics": max_topics, "max_replies_per_topic": max_replies},
        "instructions": _browser_instructions(mode),
        "candidates": [
            {
                "id": int(item.get("id", 0) or 0),
                "title": item.get("title", ""),
                "url": item.get("url") or f"https://linux.do/t/topic/{item.get('id')}",
                "surf_score": item.get("surf_score", 0),
            }
            for item in candidates[:max_topics]
        ],
    }


def _normalize_state(state: dict[str, Any]) -> dict[str, Any]:
    read_ids = sorted({int(item) for item in state.get("read_topic_ids", []) if str(item).strip().isdigit()})
    synced_names = _unique([str(item).strip() for item in state.get("synced_skill_names", []) if str(item).strip()])
    return {"read_topic_ids": read_ids, "synced_skill_names": synced_names}


def _browser_instructions(mode: str) -> str:
    return (
        "请使用 Codex 内置浏览器打开候选 Linux.do 帖子。"
        "读取首帖和高价值回复，区分事实、观点、争议和行动建议。"
        f"当前模式：{mode}。不要生成固定日报，只输出本轮任务结果。"
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest D:\workSpace\codex\information\linuxdo\tests\test_linuxdo_surf.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add tools/linuxdo_surf.py tests/test_linuxdo_surf.py
git commit -m "feat: add linuxdo surf task state"
```

如果不是 Git 仓库，跳过提交并在最终说明中注明。

### Task 3: 结果提炼和 skill 证据包导出

**Files:**
- Modify: `tests/test_linuxdo_surf.py`
- Modify: `tools/linuxdo_surf.py`

- [ ] **Step 1: 写失败测试**

追加测试：

```python
def test_build_mode_result_marks_read_topics_and_keeps_action_items():
    task = {
        "mode": "research",
        "query": "Codex 工作流",
        "candidates": [{"id": 2, "title": "Codex 长任务工作流", "url": "https://linux.do/t/topic/2"}],
    }
    readings = [
        {
            "id": 2,
            "summary": "帖子认为长任务需要计划、验证和交接。",
            "positive_feedback": ["计划明确后 Codex 表现更稳"],
            "negative_feedback": ["上下文过长会变贵"],
            "tools": ["Codex", "handoff"],
            "action_items": ["把 handoff 写进工作流"],
        }
    ]

    result = linuxdo_surf.build_mode_result(task, readings)

    assert result["mode"] == "research"
    assert result["read_topic_ids"] == [2]
    assert result["items"][0]["action_items"] == ["把 handoff 写进工作流"]


def test_build_skill_evidence_package_extracts_matching_skill_feedback():
    readings = [
        {
            "id": 10,
            "url": "https://linux.do/t/topic/10",
            "title": "skill-creator 使用经验",
            "summary": "skill-creator 适合创建新 skill，但不该塞太多背景。",
            "positive_feedback": ["触发条件清晰很有用"],
            "negative_feedback": ["过度设计会降低触发准确度"],
            "tools": ["skill-creator"],
        }
    ]

    package = linuxdo_surf.build_skill_evidence_package(["skill-creator", "other-skill"], readings)

    assert package["evidence"][0]["skill_name"] == "skill-creator"
    assert package["evidence"][0]["sync_target"] == "community/skill_reviews.json"
    assert package["evidence"][0]["topic_links"] == ["https://linux.do/t/topic/10"]
    assert package["evidence"][0]["positive_feedback"] == ["触发条件清晰很有用"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest D:\workSpace\codex\information\linuxdo\tests\test_linuxdo_surf.py -q`

Expected: FAIL，因为结果和证据包函数不存在。

- [ ] **Step 3: 写最小实现**

在 `tools/linuxdo_surf.py` 中追加：

```python
def build_mode_result(task: dict[str, Any], readings: list[dict[str, Any]]) -> dict[str, Any]:
    items = []
    for reading in readings:
        items.append(
            {
                "id": int(reading.get("id", 0) or 0),
                "title": reading.get("title", ""),
                "url": reading.get("url", ""),
                "summary": reading.get("summary", ""),
                "positive_feedback": reading.get("positive_feedback", []),
                "negative_feedback": reading.get("negative_feedback", []),
                "tools": reading.get("tools", []),
                "action_items": reading.get("action_items", []),
            }
        )
    return {
        "mode": task.get("mode", ""),
        "query": task.get("query", ""),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "read_topic_ids": sorted({item["id"] for item in items if item["id"]}),
        "items": items,
    }


def build_skill_evidence_package(skill_names: list[str], readings: list[dict[str, Any]]) -> dict[str, Any]:
    evidence = []
    for skill_name in skill_names:
        matched = [_reading for _reading in readings if _mentions_skill(_reading, skill_name)]
        if not matched:
            continue
        evidence.append(
            {
                "skill_name": skill_name,
                "topic_links": _unique([str(item.get("url", "")) for item in matched if item.get("url")]),
                "positive_feedback": _flatten_unique(matched, "positive_feedback"),
                "negative_feedback": _flatten_unique(matched, "negative_feedback"),
                "comparison_notes": _flatten_unique(matched, "comparison_notes"),
                "risk_notes": _flatten_unique(matched, "risk_notes") or _flatten_unique(matched, "negative_feedback"),
                "trial_recommendation": _trial_recommendation(matched),
                "sync_target": "community/skill_reviews.json",
            }
        )
    return {"created_at": datetime.now().isoformat(timespec="seconds"), "evidence": evidence}


def _mentions_skill(reading: dict[str, Any], skill_name: str) -> bool:
    haystack = " ".join(
        [
            str(reading.get("title", "")),
            str(reading.get("summary", "")),
            " ".join(str(item) for item in reading.get("tools", []) or []),
        ]
    ).lower()
    return skill_name.lower() in haystack


def _flatten_unique(items: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for item in items:
        raw = item.get(field, [])
        if isinstance(raw, str):
            raw = [raw]
        values.extend(str(value) for value in raw if str(value).strip())
    return _unique(values)


def _trial_recommendation(readings: list[dict[str, Any]]) -> str:
    negatives = _flatten_unique(readings, "negative_feedback") + _flatten_unique(readings, "risk_notes")
    positives = _flatten_unique(readings, "positive_feedback")
    if positives and not negatives:
        return "建议试用"
    if positives and negatives:
        return "可小范围试用，注意风险"
    return "仅记录证据，暂不建议启用"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest D:\workSpace\codex\information\linuxdo\tests\test_linuxdo_surf.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add tools/linuxdo_surf.py tests/test_linuxdo_surf.py
git commit -m "feat: add linuxdo surf evidence export"
```

如果不是 Git 仓库，跳过提交并在最终说明中注明。

### Task 4: CLI 入口和端到端文件输出

**Files:**
- Modify: `tests/test_linuxdo_surf.py`
- Modify: `tools/linuxdo_surf.py`

- [ ] **Step 1: 写失败测试**

追加测试：

```python
def test_cli_plan_writes_browser_task_and_state(tmp_path):
    topics_path = tmp_path / "topics.json"
    topics_path.write_text(
        json.dumps(
            {
                "topics": [
                    {
                        "id": 2,
                        "title": "Codex 长任务工作流经验",
                        "url": "https://linux.do/t/topic/2",
                        "first_text": "讨论 codex workflow skill",
                        "like_count": 5,
                        "reply_count": 2,
                        "views": 100,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"
    state_path = tmp_path / "state.json"

    exit_code = linuxdo_surf.main(
        [
            "plan",
            "--mode",
            "research",
            "--query",
            "Codex 工作流",
            "--topics",
            str(topics_path),
            "--output",
            str(out_dir),
            "--state",
            str(state_path),
            "--max-topics",
            "1",
        ]
    )

    assert exit_code == 0
    task = json.loads((out_dir / "browser_task_research.json").read_text(encoding="utf-8"))
    assert task["candidates"][0]["id"] == 2
    assert state_path.exists()


def test_cli_evidence_writes_skill_evidence_package(tmp_path):
    readings_path = tmp_path / "readings.json"
    readings_path.write_text(
        json.dumps(
            {
                "readings": [
                    {
                        "id": 10,
                        "title": "skill-creator 使用经验",
                        "url": "https://linux.do/t/topic/10",
                        "summary": "skill-creator 很适合创建 skill。",
                        "positive_feedback": ["好用"],
                        "tools": ["skill-creator"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    exit_code = linuxdo_surf.main(
        [
            "evidence",
            "--skills",
            "skill-creator",
            "--readings",
            str(readings_path),
            "--output",
            str(out_dir),
        ]
    )

    assert exit_code == 0
    package = json.loads((out_dir / "skill_evidence_package.json").read_text(encoding="utf-8"))
    assert package["evidence"][0]["skill_name"] == "skill-creator"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest D:\workSpace\codex\information\linuxdo\tests\test_linuxdo_surf.py -q`

Expected: FAIL，因为 CLI 尚未实现。

- [ ] **Step 3: 写最小实现**

在 `tools/linuxdo_surf.py` 中追加 CLI：

```python
def load_topics(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    return data.get("topics", [])


def load_readings(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    return data.get("readings") or data.get("topics") or []


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def run_plan(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    topics = load_topics(args.topics)
    skill_names = _split_cli_values(args.skills)
    candidates = rank_topics(
        topics,
        mode=args.mode,
        query=args.query,
        skill_names=skill_names,
        read_ids=set(state["read_topic_ids"]),
        limit=args.max_topics,
    )
    task = build_browser_task(args.mode, args.query, candidates, skill_names, args.max_topics, args.max_replies)
    write_json(args.output / f"browser_task_{args.mode}.json", task)
    save_state(args.state, state)
    return 0


def run_evidence(args: argparse.Namespace) -> int:
    skill_names = _split_cli_values(args.skills)
    readings = load_readings(args.readings)
    package = build_skill_evidence_package(skill_names, readings)
    write_json(args.output / "skill_evidence_package.json", package)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Linux.do 任务型冲浪工具。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="生成 Codex 内置浏览器阅读任务包。")
    plan.add_argument("--mode", required=True, choices=sorted(MODES))
    plan.add_argument("--query", default="")
    plan.add_argument("--skills", nargs="*", default=[])
    plan.add_argument("--topics", type=Path, default=Path("output/linuxdo_skill_research/topic_details_top220.json"))
    plan.add_argument("--output", type=Path, default=Path("output/linuxdo_surf"))
    plan.add_argument("--state", type=Path, default=Path("state/linuxdo_surf_state.json"))
    plan.add_argument("--max-topics", type=int, default=10)
    plan.add_argument("--max-replies", type=int, default=8)
    plan.set_defaults(func=run_plan)

    evidence = subparsers.add_parser("evidence", help="从阅读结果生成 skill 管理证据包。")
    evidence.add_argument("--skills", nargs="+", required=True)
    evidence.add_argument("--readings", type=Path, required=True)
    evidence.add_argument("--output", type=Path, default=Path("output/linuxdo_surf"))
    evidence.set_defaults(func=run_evidence)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.mode = validate_mode(args.mode) if hasattr(args, "mode") else ""
    return args.func(args)


def _split_cli_values(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        result.extend(_split_terms(value))
    return _unique(result)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest D:\workSpace\codex\information\linuxdo\tests\test_linuxdo_surf.py -q`

Expected: PASS。

- [ ] **Step 5: 运行基本 CLI 验证**

Run:

```bash
python D:\workSpace\codex\information\linuxdo\tools\linuxdo_surf.py plan --mode research --query "Codex 工作流" --topics D:\workSpace\codex\information\linuxdo\output\linuxdo_skill_research\topic_details_top220.json --output D:\workSpace\codex\information\linuxdo\output\linuxdo_surf --state D:\workSpace\codex\information\linuxdo\state\linuxdo_surf_state.json --max-topics 3
```

Expected: `D:\workSpace\codex\information\linuxdo\output\linuxdo_surf\browser_task_research.json` 生成，且包含候选帖子。

- [ ] **Step 6: 提交**

```bash
git add tools/linuxdo_surf.py tests/test_linuxdo_surf.py
git commit -m "feat: add linuxdo surf cli"
```

如果不是 Git 仓库，跳过提交并在最终说明中注明。

## 自检

- 规格覆盖：计划覆盖四种模式、Codex 内置浏览器阅读任务包、Windows 优先、去重状态、skill 管理证据导出、不做固定日报。
- 占位扫描：无 TBD、TODO、implement later。
- 类型一致性：核心数据都使用 `dict[str, Any]`、`list[dict[str, Any]]`、`Path`；CLI 子命令只调用已定义函数。
