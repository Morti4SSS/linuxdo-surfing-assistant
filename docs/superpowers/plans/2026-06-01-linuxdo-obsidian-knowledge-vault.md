# Linux.do Obsidian Knowledge Vault Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working version of the Linux.do surfing persistence layer that keeps lightweight machine state, avoids rereading cold history, writes curated Obsidian pages, and syncs human feedback back into future surfing decisions.

**Architecture:** Keep `tools/linuxdo_surf.py` as the CLI entrypoint and add a focused `tools/linuxdo_knowledge/` package for knowledge-state, bookmark diffing, reading strategy, Obsidian writing, feedback sync, and maintenance. The implementation is JSON/Markdown-first: hot indexes are small JSON files, cold topic/evidence history is sharded, and Obsidian is treated as the human-facing editable layer rather than the source of all machine state.

**Tech Stack:** Python 3 standard library, `argparse`, `unittest`, JSON/JSONL storage, Markdown files with YAML-like frontmatter, local filesystem paths.

---

## Scope

This plan implements the first version from [the approved spec](/Users/mortisss/Documents/linuxdo/docs/superpowers/specs/2026-06-01-linuxdo-obsidian-knowledge-vault-design.md).

It does:

- Create and maintain `/Users/mortisss/Documents/linuxdo/state/knowledge/` hot indexes and cold shards.
- Treat legacy `readings_all.json` as cold archive and never load it during normal startup.
- Incrementally read LinuxDo Scripts bookmark JSON into `bookmark_source_index.json` and `frontier_queue.json`.
- Generate batch reading tasks with `Level 0` through `Level 3`, DOM/text-first extraction guidance, and render-on-demand reasons.
- Ingest batch readings into machine state and write one Obsidian session report per batch.
- Create or update resource, candidate, comparison, workflow, wiki draft, archive, and category Markdown pages with stable frontmatter IDs.
- Preserve `## 我的反馈` exactly when rewriting existing Obsidian pages.
- Sync changed Obsidian feedback into machine state at goal startup.
- Add a lightweight maintenance command that compacts hot indexes and topic summaries without loading full history.

It does not:

- Import the existing 30 batches / 611 records into the new schema.
- Directly connect to WebDAV or store WebDAV credentials.
- Poll watchlist items on a schedule.
- Crawl all Linux.do or all GitHub.
- Solve multi-device machine-state conflicts.

## File Structure

- Modify: `tools/linuxdo_surf.py`
  - Add CLI subcommands that call the new knowledge package.
  - Keep existing commands and behavior intact.
- Create: `tools/linuxdo_knowledge/__init__.py`
  - Expose package version and public helper names.
- Create: `tools/linuxdo_knowledge/config.py`
  - Load `config/knowledge_sources.json`, apply defaults, reject WebDAV credential fields.
- Create: `tools/linuxdo_knowledge/state.py`
  - Own hot index files, cold topic summaries, evidence shards, JSON helpers, and maintenance compaction.
- Create: `tools/linuxdo_knowledge/bookmarks.py`
  - Parse LinuxDo Scripts bookmark exports and diff them into the frontier queue.
- Create: `tools/linuxdo_knowledge/strategy.py`
  - Decide reading level, skip reason, render policy, and batch task shape.
- Create: `tools/linuxdo_knowledge/obsidian.py`
  - Scaffold vault structure and write Markdown pages while preserving `## 我的反馈`.
- Create: `tools/linuxdo_knowledge/feedback.py`
  - Scan modified Obsidian files since last sync and update user feedback state.
- Create: `tools/linuxdo_knowledge/session.py`
  - Ingest one batch of readings, update state, append evidence shards, and call Obsidian writers.
- Create: `tests/test_linuxdo_knowledge.py`
  - Unit tests for the new package and CLI subcommands.
- Modify: `README.md`
  - Document the new first-version workflow and commands.
- Create: `config/knowledge_sources.example.json`
  - Example config without secrets.

## Commands Added

All commands run from `/Users/mortisss/Documents/linuxdo`:

```bash
python3 tools/linuxdo_surf.py knowledge-init --config config/knowledge_sources.json
python3 tools/linuxdo_surf.py feedback-sync --config config/knowledge_sources.json
python3 tools/linuxdo_surf.py bookmark-sync --config config/knowledge_sources.json
python3 tools/linuxdo_surf.py knowledge-plan --config config/knowledge_sources.json --batch-size 20
python3 tools/linuxdo_surf.py knowledge-session --config config/knowledge_sources.json --task output/linuxdo_surf/knowledge_task_latest.json --readings output/linuxdo_surf/knowledge_readings.json
python3 tools/linuxdo_surf.py knowledge-maintain --config config/knowledge_sources.json
```

---

### Task 1: Create Config Loader And State Skeleton

**Files:**
- Create: `tools/linuxdo_knowledge/__init__.py`
- Create: `tools/linuxdo_knowledge/config.py`
- Create: `tools/linuxdo_knowledge/state.py`
- Create: `tests/test_linuxdo_knowledge.py`
- Modify: `tools/linuxdo_surf.py`
- Create: `config/knowledge_sources.example.json`

- [ ] **Step 1: Write failing tests for config and state init**

Add `tests/test_linuxdo_knowledge.py`:

```python
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SURF_PATH = ROOT / "tools" / "linuxdo_surf.py"
surf_spec = importlib.util.spec_from_file_location("linuxdo_surf", SURF_PATH)
linuxdo_surf = importlib.util.module_from_spec(surf_spec)
surf_spec.loader.exec_module(linuxdo_surf)


class TemporaryDirectoryPath:
    def __enter__(self):
        from tempfile import TemporaryDirectory

        self._temporary_directory = TemporaryDirectory()
        return Path(self._temporary_directory.name)

    def __exit__(self, exc_type, exc, traceback):
        self._temporary_directory.cleanup()


class KnowledgeConfigAndStateTests(unittest.TestCase):
    def test_load_config_applies_defaults_and_rejects_webdav_credentials(self):
        from tools.linuxdo_knowledge.config import load_config

        with TemporaryDirectoryPath() as tmp_path:
            config_path = tmp_path / "knowledge_sources.json"
            config_path.write_text(
                json.dumps(
                    {
                        "obsidian_vault_path": str(tmp_path / "vault"),
                        "linuxdo_scripts_bookmarks": {
                            "enabled": True,
                            "path": str(tmp_path / "bookmarks.json"),
                            "webdav_password": "must-not-be-here",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "WebDAV"):
                load_config(config_path)

    def test_knowledge_init_creates_hot_indexes_and_cold_directories(self):
        from tools.linuxdo_knowledge.config import KnowledgeConfig
        from tools.linuxdo_knowledge.state import ensure_knowledge_state

        with TemporaryDirectoryPath() as tmp_path:
            config = KnowledgeConfig(
                project_root=tmp_path,
                state_root=tmp_path / "state" / "knowledge",
                obsidian_vault_path=tmp_path / "vault",
                bookmark_path=tmp_path / "bookmarks.json",
                fallback_bookmark_path=tmp_path / "bookmarkData.json",
                chrome_context_enabled=True,
                github_verification_enabled=True,
            )

            ensure_knowledge_state(config)

            state_root = tmp_path / "state" / "knowledge"
            self.assertTrue((state_root / "topic_index.json").exists())
            self.assertTrue((state_root / "topic_update_state.json").exists())
            self.assertTrue((state_root / "resource_index.json").exists())
            self.assertTrue((state_root / "claim_index.json").exists())
            self.assertTrue((state_root / "frontier_queue.json").exists())
            self.assertTrue((state_root / "topic_summaries").is_dir())
            self.assertTrue((state_root / "evidence_shards").is_dir())
            self.assertTrue((state_root / "archive").is_dir())

    def test_cli_knowledge_init_uses_config_and_creates_state(self):
        with TemporaryDirectoryPath() as tmp_path:
            config_path = tmp_path / "knowledge_sources.json"
            config_path.write_text(
                json.dumps(
                    {
                        "obsidian_vault_path": str(tmp_path / "vault"),
                        "linuxdo_scripts_bookmarks": {
                            "enabled": True,
                            "path": str(tmp_path / "bookmarks.json"),
                            "fallback_download_path": str(tmp_path / "bookmarkData.json"),
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            exit_code = linuxdo_surf.main(["knowledge-init", "--config", str(config_path)])

            self.assertEqual(exit_code, 0)
            self.assertTrue((tmp_path / "state" / "knowledge" / "topic_index.json").exists())
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest tests/test_linuxdo_knowledge.py -q
```

Expected: errors because `tools/linuxdo_knowledge` and `knowledge-init` do not exist.

- [ ] **Step 3: Create package and config implementation**

Create `tools/linuxdo_knowledge/__init__.py`:

```python
"""Lightweight persistence and Obsidian helpers for Linux.do surfing."""

__all__ = ["__version__"]
__version__ = "0.1.0"
```

Create `tools/linuxdo_knowledge/config.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


FORBIDDEN_CONFIG_KEYS = {
    "webdav_password",
    "webdav_token",
    "webdav_username",
    "webdav_account",
    "password",
    "token",
}


@dataclass(frozen=True)
class KnowledgeConfig:
    project_root: Path
    state_root: Path
    obsidian_vault_path: Path
    bookmark_path: Path | None
    fallback_bookmark_path: Path | None
    chrome_context_enabled: bool
    github_verification_enabled: bool


def load_config(path: Path) -> KnowledgeConfig:
    config_path = path.expanduser().resolve()
    data = _read_json_object(config_path)
    _reject_secret_keys(data)
    project_root = _infer_project_root(config_path)
    bookmark_config = data.get("linuxdo_scripts_bookmarks", {})
    if not isinstance(bookmark_config, dict):
        bookmark_config = {}
    chrome_config = data.get("chrome_context", {})
    if not isinstance(chrome_config, dict):
        chrome_config = {}
    github_config = data.get("github_verification", {})
    if not isinstance(github_config, dict):
        github_config = {}

    vault_raw = str(data.get("obsidian_vault_path") or project_root / "vault")
    bookmark_raw = bookmark_config.get("path")
    fallback_raw = bookmark_config.get("fallback_download_path")
    state_raw = data.get("state_root") or project_root / "state" / "knowledge"

    return KnowledgeConfig(
        project_root=project_root,
        state_root=_resolve_path(project_root, state_raw),
        obsidian_vault_path=_resolve_path(project_root, vault_raw),
        bookmark_path=_resolve_optional_path(project_root, bookmark_raw),
        fallback_bookmark_path=_resolve_optional_path(project_root, fallback_raw),
        chrome_context_enabled=bool(chrome_config.get("enabled", True)),
        github_verification_enabled=bool(github_config.get("enabled", True)),
    )


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("配置文件顶层必须是 JSON object")
    return data


def _reject_secret_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).lower() in FORBIDDEN_CONFIG_KEYS:
                raise ValueError("配置文件不能保存 WebDAV 或账号凭证")
            _reject_secret_keys(nested)
    elif isinstance(value, list):
        for item in value:
            _reject_secret_keys(item)


def _infer_project_root(config_path: Path) -> Path:
    if config_path.parent.name == "config":
        return config_path.parent.parent
    return config_path.parent


def _resolve_path(project_root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else project_root / path


def _resolve_optional_path(project_root: Path, value: Any) -> Path | None:
    if value is None or str(value).strip() == "":
        return None
    return _resolve_path(project_root, str(value))
```

- [ ] **Step 4: Create state skeleton implementation**

Create `tools/linuxdo_knowledge/state.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import KnowledgeConfig


HOT_INDEX_DEFAULTS: dict[str, Any] = {
    "topic_index.json": {"topics": {}},
    "topic_update_state.json": {"topics": {}},
    "resource_index.json": {"resources": {}},
    "claim_index.json": {"claims": {}},
    "feedback_sync_state.json": {"last_sync_at": None, "files": {}},
    "user_feedback.json": {"items": []},
    "frontier_queue.json": {"items": []},
    "bookmark_source_index.json": {"bookmarks": {}},
}


@dataclass(frozen=True)
class KnowledgePaths:
    root: Path
    topic_index: Path
    topic_update_state: Path
    resource_index: Path
    claim_index: Path
    feedback_sync_state: Path
    user_feedback: Path
    frontier_queue: Path
    bookmark_source_index: Path
    session_log: Path
    topic_summaries: Path
    evidence_shards: Path
    archive: Path


def paths_for(config: KnowledgeConfig) -> KnowledgePaths:
    root = config.state_root
    return KnowledgePaths(
        root=root,
        topic_index=root / "topic_index.json",
        topic_update_state=root / "topic_update_state.json",
        resource_index=root / "resource_index.json",
        claim_index=root / "claim_index.json",
        feedback_sync_state=root / "feedback_sync_state.json",
        user_feedback=root / "user_feedback.json",
        frontier_queue=root / "frontier_queue.json",
        bookmark_source_index=root / "bookmark_source_index.json",
        session_log=root / "session_log.jsonl",
        topic_summaries=root / "topic_summaries",
        evidence_shards=root / "evidence_shards",
        archive=root / "archive",
    )


def ensure_knowledge_state(config: KnowledgeConfig) -> KnowledgePaths:
    paths = paths_for(config)
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.topic_summaries.mkdir(parents=True, exist_ok=True)
    paths.evidence_shards.mkdir(parents=True, exist_ok=True)
    paths.archive.mkdir(parents=True, exist_ok=True)
    for filename, default_value in HOT_INDEX_DEFAULTS.items():
        target = paths.root / filename
        if not target.exists():
            write_json(target, default_value)
    if not paths.session_log.exists():
        paths.session_log.write_text("", encoding="utf-8")
    return paths


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
```

- [ ] **Step 5: Add CLI subcommand**

Modify `tools/linuxdo_surf.py`.

Add imports near existing imports:

```python
from tools.linuxdo_knowledge.config import load_config
from tools.linuxdo_knowledge.state import ensure_knowledge_state
```

Add command function near existing `run_*` functions:

```python
def run_knowledge_init(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    ensure_knowledge_state(config)
    return 0
```

Add parser entry in `build_parser()` before `return parser`:

```python
    knowledge_init = subparsers.add_parser("knowledge-init", help="初始化知识库机器状态目录。")
    knowledge_init.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    knowledge_init.set_defaults(func=run_knowledge_init)
```

Keep `main()` unchanged except that the new command must not require `args.mode`.

- [ ] **Step 6: Add example config**

Create `config/knowledge_sources.example.json`:

```json
{
  "obsidian_vault_path": "/absolute/path/to/Obsidian/LinuxdoKnowledge",
  "state_root": "state/knowledge",
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

- [ ] **Step 7: Run tests**

Run:

```bash
python3 -m unittest tests/test_linuxdo_surf.py tests/test_linuxdo_knowledge.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add tools/linuxdo_surf.py tools/linuxdo_knowledge tests/test_linuxdo_knowledge.py config/knowledge_sources.example.json
git commit -m "feat: initialize knowledge state"
```

---

### Task 2: Implement Hot Index And Cold History State Operations

**Files:**
- Modify: `tools/linuxdo_knowledge/state.py`
- Modify: `tests/test_linuxdo_knowledge.py`

- [ ] **Step 1: Write failing tests for topic state, summaries, and evidence shards**

Append to `tests/test_linuxdo_knowledge.py`:

```python
class KnowledgeStateOperationTests(unittest.TestCase):
    def test_hot_index_ignores_legacy_readings_all(self):
        from tools.linuxdo_knowledge.config import KnowledgeConfig
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, load_hot_indexes

        with TemporaryDirectoryPath() as tmp_path:
            config = KnowledgeConfig(
                project_root=tmp_path,
                state_root=tmp_path / "state" / "knowledge",
                obsidian_vault_path=tmp_path / "vault",
                bookmark_path=None,
                fallback_bookmark_path=None,
                chrome_context_enabled=True,
                github_verification_enabled=True,
            )
            ensure_knowledge_state(config)
            (config.state_root / "readings_all.json").write_text("{not valid json", encoding="utf-8")

            indexes = load_hot_indexes(config)

            self.assertEqual(indexes["topic_index"], {"topics": {}})
            self.assertEqual(indexes["frontier_queue"], {"items": []})

    def test_upsert_topic_summary_and_evidence_shard(self):
        from tools.linuxdo_knowledge.config import KnowledgeConfig
        from tools.linuxdo_knowledge.state import (
            append_evidence,
            ensure_knowledge_state,
            load_json,
            upsert_topic_summary,
        )

        with TemporaryDirectoryPath() as tmp_path:
            config = KnowledgeConfig(
                project_root=tmp_path,
                state_root=tmp_path / "state" / "knowledge",
                obsidian_vault_path=tmp_path / "vault",
                bookmark_path=None,
                fallback_bookmark_path=None,
                chrome_context_enabled=True,
                github_verification_enabled=True,
            )
            ensure_knowledge_state(config)

            summary_path = upsert_topic_summary(
                config,
                topic_id=123,
                summary={
                    "topic_id": 123,
                    "title": "Codex workflow",
                    "key_points": ["Level 1 足够"],
                    "resource_ids": ["resource:codex-workflow"],
                    "claim_ids": ["claim:context-budget"],
                },
            )
            append_evidence(
                config,
                {
                    "source_type": "linuxdo_topic",
                    "source_url": "https://linux.do/t/topic/123",
                    "topic_id": 123,
                    "summary": "回复指出只读新增楼层可省 token。",
                    "evidence_status": "supporting",
                },
                observed_at="2026-06-01T12:00:00",
            )

            summary = load_json(summary_path, {})
            shard_text = (config.state_root / "evidence_shards" / "2026-06.jsonl").read_text(encoding="utf-8")

            self.assertEqual(summary["topic_id"], 123)
            self.assertIn("只读新增楼层", shard_text)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest tests/test_linuxdo_knowledge.py -q
```

Expected: failures because `load_hot_indexes`, `upsert_topic_summary`, and `append_evidence` do not exist.

- [ ] **Step 3: Implement hot index loading and cold writes**

Append to `tools/linuxdo_knowledge/state.py`:

```python
def load_hot_indexes(config: KnowledgeConfig) -> dict[str, Any]:
    paths = ensure_knowledge_state(config)
    return {
        "topic_index": load_json(paths.topic_index, {"topics": {}}),
        "topic_update_state": load_json(paths.topic_update_state, {"topics": {}}),
        "resource_index": load_json(paths.resource_index, {"resources": {}}),
        "claim_index": load_json(paths.claim_index, {"claims": {}}),
        "feedback_sync_state": load_json(paths.feedback_sync_state, {"last_sync_at": None, "files": {}}),
        "user_feedback": load_json(paths.user_feedback, {"items": []}),
        "frontier_queue": load_json(paths.frontier_queue, {"items": []}),
        "bookmark_source_index": load_json(paths.bookmark_source_index, {"bookmarks": {}}),
    }


def save_hot_index(config: KnowledgeConfig, name: str, data: Any) -> None:
    paths = ensure_knowledge_state(config)
    targets = {
        "topic_index": paths.topic_index,
        "topic_update_state": paths.topic_update_state,
        "resource_index": paths.resource_index,
        "claim_index": paths.claim_index,
        "feedback_sync_state": paths.feedback_sync_state,
        "user_feedback": paths.user_feedback,
        "frontier_queue": paths.frontier_queue,
        "bookmark_source_index": paths.bookmark_source_index,
    }
    if name not in targets:
        raise ValueError(f"未知热索引：{name}")
    write_json(targets[name], data)


def topic_summary_path(config: KnowledgeConfig, topic_id: int | str) -> Path:
    paths = ensure_knowledge_state(config)
    return paths.topic_summaries / f"{int(topic_id)}.json"


def upsert_topic_summary(config: KnowledgeConfig, topic_id: int | str, summary: dict[str, Any]) -> Path:
    path = topic_summary_path(config, topic_id)
    existing = load_json(path, {})
    merged = {**existing, **summary, "topic_id": int(topic_id), "updated_at": now_iso()}
    write_json(path, merged)
    return path


def append_evidence(config: KnowledgeConfig, evidence: dict[str, Any], observed_at: str | None = None) -> Path:
    observed = observed_at or now_iso()
    month = observed[:7]
    paths = ensure_knowledge_state(config)
    target = paths.evidence_shards / f"{month}.jsonl"
    append_jsonl(target, {**evidence, "observed_at": observed})
    return target
```

- [ ] **Step 4: Run tests**

Run:

```bash
python3 -m unittest tests/test_linuxdo_knowledge.py -q
```

Expected: all new tests pass.

- [ ] **Step 5: Commit**

```bash
git add tools/linuxdo_knowledge/state.py tests/test_linuxdo_knowledge.py
git commit -m "feat: add knowledge hot and cold state"
```

---

### Task 3: Sync LinuxDo Scripts Bookmarks Into Frontier Queue

**Files:**
- Create: `tools/linuxdo_knowledge/bookmarks.py`
- Modify: `tools/linuxdo_surf.py`
- Modify: `tests/test_linuxdo_knowledge.py`

- [ ] **Step 1: Write failing tests for bookmark parsing and incremental diff**

Append to `tests/test_linuxdo_knowledge.py`:

```python
class BookmarkSyncTests(unittest.TestCase):
    def test_parse_linuxdo_scripts_bookmarks_flattens_groups(self):
        from tools.linuxdo_knowledge.bookmarks import parse_bookmark_export

        data = [
            {
                "id": 0,
                "name": "Skills / Plugins",
                "list": [
                    {
                        "cate": "开发调优",
                        "tags": ["skill", "实测"],
                        "timestamp": 1780151443336,
                        "title": "某 skill 讨论",
                        "url": "https://linux.do/t/topic/2273499",
                    }
                ],
            }
        ]

        items = parse_bookmark_export(data)

        self.assertEqual(items[0]["folder"], "Skills / Plugins")
        self.assertEqual(items[0]["topic_id"], 2273499)
        self.assertEqual(items[0]["tags"], ["skill", "实测"])

    def test_sync_bookmarks_adds_new_url_and_updates_metadata_without_duplicate_frontier(self):
        from tools.linuxdo_knowledge.bookmarks import sync_bookmarks
        from tools.linuxdo_knowledge.config import KnowledgeConfig
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, load_hot_indexes

        with TemporaryDirectoryPath() as tmp_path:
            bookmark_path = tmp_path / "bookmarks.json"
            config = KnowledgeConfig(
                project_root=tmp_path,
                state_root=tmp_path / "state" / "knowledge",
                obsidian_vault_path=tmp_path / "vault",
                bookmark_path=bookmark_path,
                fallback_bookmark_path=None,
                chrome_context_enabled=True,
                github_verification_enabled=True,
            )
            ensure_knowledge_state(config)
            bookmark_path.write_text(
                json.dumps(
                    [{"name": "AI Coding / Workflow", "list": [{"title": "工作流", "url": "https://linux.do/t/topic/1", "tags": ["workflow"]}]}],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            first = sync_bookmarks(config, seen_at="2026-06-01T12:00:00")
            bookmark_path.write_text(
                json.dumps(
                    [{"name": "To Verify", "list": [{"title": "工作流", "url": "https://linux.do/t/topic/1", "tags": ["workflow", "待验证"]}]}],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            second = sync_bookmarks(config, seen_at="2026-06-01T13:00:00")
            indexes = load_hot_indexes(config)

            self.assertEqual(first["new"], 1)
            self.assertEqual(second["metadata_changed"], 1)
            self.assertEqual(len(indexes["frontier_queue"]["items"]), 1)
            self.assertEqual(indexes["bookmark_source_index"]["bookmarks"]["https://linux.do/t/topic/1"]["folder"], "To Verify")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest tests/test_linuxdo_knowledge.py -q
```

Expected: failures because bookmark functions do not exist.

- [ ] **Step 3: Implement bookmark parser and diff**

Create `tools/linuxdo_knowledge/bookmarks.py`:

```python
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .config import KnowledgeConfig
from .state import load_hot_indexes, now_iso, save_hot_index


TOPIC_RE = re.compile(r"linux\.do/t/(?:topic/)?(\d+)")


def parse_bookmark_export(data: Any) -> list[dict[str, Any]]:
    groups = data if isinstance(data, list) else []
    results: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        folder = str(group.get("name") or "默认")
        for raw_item in group.get("list", []) or []:
            if not isinstance(raw_item, dict):
                continue
            url = str(raw_item.get("url") or "").strip()
            topic_id = extract_topic_id(url)
            if not url or topic_id is None:
                continue
            tags = [str(tag) for tag in raw_item.get("tags", []) or [] if str(tag).strip()]
            item = {
                "url": url,
                "topic_id": topic_id,
                "title": str(raw_item.get("title") or ""),
                "folder": folder,
                "cate": str(raw_item.get("cate") or ""),
                "tags": tags,
                "timestamp": raw_item.get("timestamp"),
            }
            item["content_hash"] = bookmark_hash(item)
            results.append(item)
    return results


def extract_topic_id(url: str) -> int | None:
    match = TOPIC_RE.search(url)
    if not match:
        return None
    return int(match.group(1))


def bookmark_hash(item: dict[str, Any]) -> str:
    payload = {
        "title": item.get("title", ""),
        "folder": item.get("folder", ""),
        "cate": item.get("cate", ""),
        "tags": item.get("tags", []),
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def load_bookmark_export(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sync_bookmarks(config: KnowledgeConfig, seen_at: str | None = None) -> dict[str, int]:
    seen = seen_at or now_iso()
    path = _select_bookmark_path(config)
    if path is None:
        return {"new": 0, "metadata_changed": 0, "unchanged": 0}
    items = parse_bookmark_export(load_bookmark_export(path))
    indexes = load_hot_indexes(config)
    source_index = indexes["bookmark_source_index"]
    frontier = indexes["frontier_queue"]
    bookmarks = source_index.setdefault("bookmarks", {})
    frontier_items = frontier.setdefault("items", [])
    frontier_urls = {str(item.get("url")) for item in frontier_items if isinstance(item, dict)}
    counts = {"new": 0, "metadata_changed": 0, "unchanged": 0}
    for item in items:
        url = item["url"]
        existing = bookmarks.get(url)
        if existing is None:
            bookmarks[url] = {**item, "first_seen_at": seen, "last_seen_at": seen, "last_processed_at": None, "processing_status": "new"}
            if url not in frontier_urls:
                frontier_items.append(_frontier_item(item, seen, "bookmark:new"))
                frontier_urls.add(url)
            counts["new"] += 1
        elif existing.get("content_hash") != item["content_hash"]:
            bookmarks[url] = {**existing, **item, "last_seen_at": seen, "processing_status": "metadata_changed"}
            _bump_frontier(frontier_items, url, item)
            counts["metadata_changed"] += 1
        else:
            existing["last_seen_at"] = seen
            counts["unchanged"] += 1
    save_hot_index(config, "bookmark_source_index", source_index)
    save_hot_index(config, "frontier_queue", frontier)
    return counts


def _select_bookmark_path(config: KnowledgeConfig) -> Path | None:
    for path in (config.bookmark_path, config.fallback_bookmark_path):
        if path and path.exists():
            return path
    return None


def _frontier_item(item: dict[str, Any], seen_at: str, reason: str) -> dict[str, Any]:
    return {
        "url": item["url"],
        "topic_id": item["topic_id"],
        "title": item["title"],
        "source": "linuxdo_scripts_bookmark",
        "priority": 80,
        "reason": reason,
        "folder": item["folder"],
        "tags": item["tags"],
        "suggested_level": 1,
        "created_at": seen_at,
        "updated_at": seen_at,
    }


def _bump_frontier(frontier_items: list[dict[str, Any]], url: str, item: dict[str, Any]) -> None:
    for frontier_item in frontier_items:
        if frontier_item.get("url") == url:
            frontier_item["folder"] = item.get("folder", "")
            frontier_item["tags"] = item.get("tags", [])
            frontier_item["priority"] = max(int(frontier_item.get("priority", 0)), 90 if "待验证" in item.get("tags", []) else 80)
            frontier_item["reason"] = "bookmark:metadata_changed"
            frontier_item["updated_at"] = now_iso()
            return
```

- [ ] **Step 4: Add CLI command**

Modify `tools/linuxdo_surf.py`.

Add import:

```python
from tools.linuxdo_knowledge.bookmarks import sync_bookmarks
```

Add function:

```python
def run_bookmark_sync(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    ensure_knowledge_state(config)
    result = sync_bookmarks(config)
    write_json(args.output, result)
    return 0
```

Add parser:

```python
    bookmark_sync = subparsers.add_parser("bookmark-sync", help="增量同步 LinuxDo Scripts 收藏到 frontier queue。")
    bookmark_sync.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    bookmark_sync.add_argument("--output", type=Path, default=Path("output/linuxdo_surf/bookmark_sync_result.json"))
    bookmark_sync.set_defaults(func=run_bookmark_sync)
```

- [ ] **Step 5: Run tests**

Run:

```bash
python3 -m unittest tests/test_linuxdo_surf.py tests/test_linuxdo_knowledge.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add tools/linuxdo_surf.py tools/linuxdo_knowledge/bookmarks.py tests/test_linuxdo_knowledge.py
git commit -m "feat: sync linuxdo bookmark frontier"
```

---

### Task 4: Build Reading Strategy And Knowledge Batch Task Generation

**Files:**
- Create: `tools/linuxdo_knowledge/strategy.py`
- Modify: `tools/linuxdo_surf.py`
- Modify: `tests/test_linuxdo_knowledge.py`

- [ ] **Step 1: Write failing tests for level decisions and task shape**

Append to `tests/test_linuxdo_knowledge.py`:

```python
class ReadingStrategyTests(unittest.TestCase):
    def test_decide_reading_level_skips_unchanged_seen_topic(self):
        from tools.linuxdo_knowledge.strategy import decide_reading_plan

        plan = decide_reading_plan(
            topic={"topic_id": 1, "title": "旧帖", "reply_count": 10, "last_activity_at": "2026-06-01T10:00:00"},
            topic_state={"read_reply_count": 10, "last_activity_at": "2026-06-01T10:00:00", "watchlist": False},
        )

        self.assertEqual(plan["level"], 0)
        self.assertEqual(plan["action"], "skip")
        self.assertIn("未变化", plan["skip_reason"])

    def test_decide_reading_level_uses_level_2_for_watchlist_updates(self):
        from tools.linuxdo_knowledge.strategy import decide_reading_plan

        plan = decide_reading_plan(
            topic={"topic_id": 1, "title": "争议工具", "reply_count": 16, "last_activity_at": "2026-06-01T11:00:00"},
            topic_state={"read_reply_count": 10, "last_activity_at": "2026-06-01T10:00:00", "watchlist": True},
        )

        self.assertEqual(plan["level"], 2)
        self.assertEqual(plan["action"], "read_incremental")

    def test_build_knowledge_task_does_not_include_legacy_history(self):
        from tools.linuxdo_knowledge.config import KnowledgeConfig
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, save_hot_index
        from tools.linuxdo_knowledge.strategy import build_knowledge_task

        with TemporaryDirectoryPath() as tmp_path:
            config = KnowledgeConfig(
                project_root=tmp_path,
                state_root=tmp_path / "state" / "knowledge",
                obsidian_vault_path=tmp_path / "vault",
                bookmark_path=None,
                fallback_bookmark_path=None,
                chrome_context_enabled=True,
                github_verification_enabled=True,
            )
            ensure_knowledge_state(config)
            (config.state_root / "readings_all.json").write_text("{not valid json", encoding="utf-8")
            save_hot_index(
                config,
                "frontier_queue",
                {"items": [{"url": "https://linux.do/t/topic/1", "topic_id": 1, "title": "Codex workflow", "priority": 80}]},
            )

            task = build_knowledge_task(config, batch_size=20, created_at="2026-06-01T12:00:00")

            self.assertEqual(task["batch_size"], 20)
            self.assertEqual(task["items"][0]["reading_level"], 1)
            self.assertEqual(task["extraction_policy"], "dom_text_first_render_on_demand")
            self.assertNotIn("readings_all", json.dumps(task, ensure_ascii=False))
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest tests/test_linuxdo_knowledge.py -q
```

Expected: failures because strategy functions do not exist.

- [ ] **Step 3: Implement strategy module**

Create `tools/linuxdo_knowledge/strategy.py`:

```python
from __future__ import annotations

from typing import Any

from .bookmarks import extract_topic_id
from .config import KnowledgeConfig
from .state import load_hot_indexes, now_iso


RENDER_SIGNALS = ["如图", "看图", "截图", "效果如下", "界面", "按钮", "UI", "WebUI", "报错图"]
HIGH_SIGNAL_WORDS = ["试了", "踩坑", "替代", "不推荐", "更新了", "解决了", "实测", "对比", "争议"]


def decide_reading_plan(topic: dict[str, Any], topic_state: dict[str, Any] | None = None) -> dict[str, Any]:
    state = topic_state or {}
    reply_count = _int(topic.get("reply_count"))
    read_reply_count = _int(state.get("read_reply_count"))
    last_activity = str(topic.get("last_activity_at") or "")
    old_activity = str(state.get("last_activity_at") or "")
    watchlist = bool(state.get("watchlist"))
    title = str(topic.get("title") or "")
    text = " ".join([title, str(topic.get("summary") or ""), " ".join(topic.get("tags", []) or [])])

    if state and reply_count == read_reply_count and last_activity == old_activity:
        return {"level": 0, "action": "skip", "skip_reason": "已读且回复数/最后活动时间未变化", "render_required": False}
    if watchlist and reply_count > read_reply_count:
        return {"level": 2, "action": "read_incremental", "skip_reason": "", "render_required": _render_required(text)}
    if any(word.lower() in text.lower() for word in HIGH_SIGNAL_WORDS):
        return {"level": 2, "action": "read", "skip_reason": "", "render_required": _render_required(text)}
    if _looks_low_value(text):
        return {"level": 0, "action": "metadata_only", "skip_reason": "低相关或低证据密度", "render_required": False}
    return {"level": 1, "action": "read", "skip_reason": "", "render_required": _render_required(text)}


def build_knowledge_task(config: KnowledgeConfig, batch_size: int = 20, created_at: str | None = None) -> dict[str, Any]:
    indexes = load_hot_indexes(config)
    topic_updates = indexes["topic_update_state"].get("topics", {})
    frontier_items = list(indexes["frontier_queue"].get("items", []))
    frontier_items.sort(key=lambda item: (-int(item.get("priority", 0)), str(item.get("title", ""))))
    task_items = []
    for item in frontier_items[:batch_size]:
        topic_id = item.get("topic_id") or extract_topic_id(str(item.get("url") or ""))
        if topic_id is None:
            continue
        topic = {
            "topic_id": topic_id,
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "tags": item.get("tags", []),
            "reply_count": item.get("reply_count", 0),
            "last_activity_at": item.get("last_activity_at", ""),
        }
        plan = decide_reading_plan(topic, topic_updates.get(str(topic_id), {}))
        task_items.append(
            {
                "topic_id": topic_id,
                "title": topic["title"],
                "url": topic["url"],
                "reading_level": plan["level"],
                "action": plan["action"],
                "skip_reason": plan["skip_reason"],
                "render_required": plan["render_required"],
                "render_policy": "only_if_dom_text_missing_visual_state_or_key_content",
                "reply_policy": _reply_policy(plan["level"]),
            }
        )
    return {
        "created_at": created_at or now_iso(),
        "batch_size": batch_size,
        "source": "knowledge_frontier_queue",
        "extraction_policy": "dom_text_first_render_on_demand",
        "history_policy": "load_hot_indexes_only",
        "items": task_items,
    }


def _reply_policy(level: int) -> str:
    policies = {
        0: "metadata only",
        1: "main post plus a few high-signal replies with minimal context",
        2: "main post plus popular, disputed, linked, author, and contextual replies",
        3: "deep read most replies because the topic affects comparison or resource choice",
    }
    return policies.get(level, policies[1])


def _render_required(text: str) -> bool:
    return any(signal.lower() in text.lower() for signal in RENDER_SIGNALS)


def _looks_low_value(text: str) -> bool:
    lowered = text.lower()
    low_words = ["签到", "水贴", "闲聊"]
    return any(word in lowered for word in low_words)


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
```

- [ ] **Step 4: Add CLI command**

Modify `tools/linuxdo_surf.py`.

Add import:

```python
from tools.linuxdo_knowledge.strategy import build_knowledge_task
```

Add function:

```python
def run_knowledge_plan(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    ensure_knowledge_state(config)
    task = build_knowledge_task(config, batch_size=args.batch_size)
    write_json(args.output, task)
    return 0
```

Add parser:

```python
    knowledge_plan = subparsers.add_parser("knowledge-plan", help="从轻量 frontier 生成一批知识库冲浪任务。")
    knowledge_plan.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    knowledge_plan.add_argument("--batch-size", type=int, default=20)
    knowledge_plan.add_argument("--output", type=Path, default=Path("output/linuxdo_surf/knowledge_task_latest.json"))
    knowledge_plan.set_defaults(func=run_knowledge_plan)
```

- [ ] **Step 5: Run tests**

Run:

```bash
python3 -m unittest tests/test_linuxdo_surf.py tests/test_linuxdo_knowledge.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add tools/linuxdo_surf.py tools/linuxdo_knowledge/strategy.py tests/test_linuxdo_knowledge.py
git commit -m "feat: plan token-efficient knowledge batches"
```

---

### Task 5: Scaffold Obsidian Vault And Preserve Human Feedback

**Files:**
- Create: `tools/linuxdo_knowledge/obsidian.py`
- Modify: `tests/test_linuxdo_knowledge.py`

- [ ] **Step 1: Write failing tests for scaffold and feedback preservation**

Append to `tests/test_linuxdo_knowledge.py`:

```python
class ObsidianWriterTests(unittest.TestCase):
    def test_scaffold_vault_creates_expected_structure_and_agent_files(self):
        from tools.linuxdo_knowledge.config import KnowledgeConfig
        from tools.linuxdo_knowledge.obsidian import scaffold_vault

        with TemporaryDirectoryPath() as tmp_path:
            config = KnowledgeConfig(
                project_root=tmp_path,
                state_root=tmp_path / "state" / "knowledge",
                obsidian_vault_path=tmp_path / "vault",
                bookmark_path=None,
                fallback_bookmark_path=None,
                chrome_context_enabled=True,
                github_verification_enabled=True,
            )

            scaffold_vault(config)

            self.assertTrue((config.obsidian_vault_path / "CLAUDE.md").exists())
            self.assertTrue((config.obsidian_vault_path / "AGENTS.md").exists())
            self.assertTrue((config.obsidian_vault_path / "catalog" / "resources").is_dir())
            self.assertTrue((config.obsidian_vault_path / "inbox" / "sessions").is_dir())

    def test_write_page_preserves_human_feedback_section(self):
        from tools.linuxdo_knowledge.config import KnowledgeConfig
        from tools.linuxdo_knowledge.obsidian import write_page

        with TemporaryDirectoryPath() as tmp_path:
            config = KnowledgeConfig(
                project_root=tmp_path,
                state_root=tmp_path / "state" / "knowledge",
                obsidian_vault_path=tmp_path / "vault",
                bookmark_path=None,
                fallback_bookmark_path=None,
                chrome_context_enabled=True,
                github_verification_enabled=True,
            )
            page_path = config.obsidian_vault_path / "catalog" / "resources" / "Superpowers.md"
            page_path.parent.mkdir(parents=True)
            page_path.write_text("# Superpowers\n\n## Agent 摘要\n旧摘要\n\n## 我的反馈\n这里不要动\n", encoding="utf-8")

            write_page(
                page_path,
                frontmatter={"id": "resource:superpowers", "type": "resource", "status": "active"},
                title="Superpowers",
                sections={"Agent 摘要": "新摘要", "解决什么问题": "确定 spec"},
            )

            text = page_path.read_text(encoding="utf-8")
            self.assertIn("新摘要", text)
            self.assertIn("## 我的反馈\n这里不要动\n", text)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest tests/test_linuxdo_knowledge.py -q
```

Expected: failures because Obsidian functions do not exist.

- [ ] **Step 3: Implement Obsidian scaffold and page writer**

Create `tools/linuxdo_knowledge/obsidian.py`:

```python
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .config import KnowledgeConfig


FEEDBACK_HEADING = "## 我的反馈"
VAULT_DIRS = [
    "wiki/concepts",
    "wiki/practices",
    "wiki/drafts",
    "wiki/notes",
    "catalog/resources",
    "catalog/candidates",
    "catalog/comparisons",
    "catalog/workflows",
    "catalog/categories",
    "catalog/archive",
    "inbox/sessions",
    "raw",
]


def scaffold_vault(config: KnowledgeConfig) -> None:
    root = config.obsidian_vault_path
    root.mkdir(parents=True, exist_ok=True)
    for directory in VAULT_DIRS:
        (root / directory).mkdir(parents=True, exist_ok=True)
    _write_if_missing(root / "CLAUDE.md", _claude_rules())
    _write_if_missing(root / "AGENTS.md", "# AGENTS\n\n请先阅读 [[CLAUDE]]，遵守知识库 schema 和 `## 我的反馈` 保护规则。\n")
    _write_if_missing(root / "index.md", "# Linux.do Knowledge Vault\n\n## 入口\n\n- [[log]]\n")
    _write_if_missing(root / "log.md", "# Log\n")


def write_page(path: Path, frontmatter: dict[str, Any], title: str, sections: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    old_text = path.read_text(encoding="utf-8") if path.exists() else ""
    feedback = _extract_feedback(old_text)
    body = [_format_frontmatter(frontmatter), f"# {title}", ""]
    for heading, content in sections.items():
        body.append(f"## {heading}")
        body.append(str(content).strip())
        body.append("")
    body.append(FEEDBACK_HEADING)
    body.append(feedback.strip() if feedback.strip() else "")
    text = "\n".join(body).rstrip() + "\n"
    path.write_text(text, encoding="utf-8")


def append_log(config: KnowledgeConfig, line: str) -> None:
    log_path = config.obsidian_vault_path / "log.md"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    existing = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Log\n"
    log_path.write_text(existing.rstrip() + "\n\n" + line.strip() + "\n", encoding="utf-8")


def page_path_for(config: KnowledgeConfig, page_type: str, name: str) -> Path:
    mapping = {
        "resource": "catalog/resources",
        "candidate": "catalog/candidates",
        "comparison": "catalog/comparisons",
        "workflow": "catalog/workflows",
        "category": "catalog/categories",
        "archive": "catalog/archive",
        "concept": "wiki/concepts",
        "practice": "wiki/practices",
        "draft": "wiki/drafts",
        "note": "wiki/notes",
        "session": "inbox/sessions",
    }
    directory = mapping.get(page_type, "wiki/notes")
    return config.obsidian_vault_path / directory / f"{safe_filename(name)}.md"


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]+", " ", name).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "Untitled"


def _write_if_missing(path: Path, text: str) -> None:
    if not path.exists():
        path.write_text(text, encoding="utf-8")


def _extract_feedback(text: str) -> str:
    if FEEDBACK_HEADING not in text:
        return ""
    return text.split(FEEDBACK_HEADING, 1)[1].strip()


def _format_frontmatter(frontmatter: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in frontmatter.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        elif isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def _claude_rules() -> str:
    return """# CLAUDE

## Knowledge Rules

- Linux.do 内容是证据和线索，不是权威事实。
- 宽收证据，严进知识。
- 不要改写 `## 我的反馈`。
- 资源页回答它解决什么问题、适用场景、限制、社区评价和来源证据。
- 对比页回答同类资源按场景怎么选。
- 过时或冲突内容用 `evidence_status` 和 `staleness_risk` 表达。
"""
```

- [ ] **Step 4: Run tests**

Run:

```bash
python3 -m unittest tests/test_linuxdo_knowledge.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add tools/linuxdo_knowledge/obsidian.py tests/test_linuxdo_knowledge.py
git commit -m "feat: write obsidian vault pages"
```

---

### Task 6: Ingest One Batch And Write One Obsidian Session

**Files:**
- Create: `tools/linuxdo_knowledge/session.py`
- Modify: `tools/linuxdo_surf.py`
- Modify: `tests/test_linuxdo_knowledge.py`

- [ ] **Step 1: Write failing tests for session ingestion**

Append to `tests/test_linuxdo_knowledge.py`:

```python
class SessionIngestionTests(unittest.TestCase):
    def test_ingest_session_updates_state_and_writes_session_report(self):
        from tools.linuxdo_knowledge.config import KnowledgeConfig
        from tools.linuxdo_knowledge.session import ingest_session
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, load_hot_indexes

        with TemporaryDirectoryPath() as tmp_path:
            config = KnowledgeConfig(
                project_root=tmp_path,
                state_root=tmp_path / "state" / "knowledge",
                obsidian_vault_path=tmp_path / "vault",
                bookmark_path=None,
                fallback_bookmark_path=None,
                chrome_context_enabled=True,
                github_verification_enabled=True,
            )
            ensure_knowledge_state(config)
            task = {
                "created_at": "2026-06-01T12:00:00",
                "items": [{"topic_id": 123, "title": "Codex workflow", "url": "https://linux.do/t/topic/123"}],
            }
            readings = {
                "readings": [
                    {
                        "topic_id": 123,
                        "title": "Codex workflow",
                        "url": "https://linux.do/t/topic/123",
                        "summary": "讨论长任务上下文预算。",
                        "value_level": "high",
                        "tags": ["workflow"],
                        "reply_count": 12,
                        "last_activity_at": "2026-06-01T11:00:00",
                        "resources": [{"id": "candidate:codex-workflow", "name": "Codex Workflow", "status": "candidate"}],
                        "claims": [{"id": "claim:context-budget", "text": "长任务需要轻量索引"}],
                        "evidence": [{"summary": "回复支持只读新增楼层。", "evidence_status": "supporting"}],
                        "comparisons": [{"id": "comparison:workflow-tools", "name": "Workflow Tools", "summary": "按 token 成本和反馈闭环比较。"}],
                        "workflows": [{"id": "workflow:linuxdo-obsidian", "name": "Linux.do Obsidian Workflow", "summary": "冲浪后写入 Obsidian。"}],
                        "knowledge_drafts": [{"id": "draft:lightweight-index", "name": "轻量索引", "summary": "热索引降低重复读取成本。"}],
                        "categories": [{"id": "category:skills", "name": "skills", "items": ["Codex Workflow"]}],
                    }
                ]
            }

            result = ingest_session(config, task=task, readings=readings, batch_id="001", observed_at="2026-06-01T12:30:00")
            indexes = load_hot_indexes(config)
            session_path = config.obsidian_vault_path / "inbox" / "sessions" / "2026-06-01-batch-001.md"

            self.assertEqual(result["readings"], 1)
            self.assertIn("123", indexes["topic_index"]["topics"])
            candidate_path = config.obsidian_vault_path / "catalog" / "candidates" / "Codex Workflow.md"
            comparison_path = config.obsidian_vault_path / "catalog" / "comparisons" / "Workflow Tools.md"
            workflow_path = config.obsidian_vault_path / "catalog" / "workflows" / "Linux.do Obsidian Workflow.md"
            draft_path = config.obsidian_vault_path / "wiki" / "drafts" / "轻量索引.md"
            category_path = config.obsidian_vault_path / "catalog" / "categories" / "skills.md"

            self.assertIn("candidate:codex-workflow", indexes["resource_index"]["resources"])
            self.assertIn("claim:context-budget", indexes["claim_index"]["claims"])
            self.assertTrue(session_path.exists())
            self.assertIn("Codex workflow", session_path.read_text(encoding="utf-8"))
            self.assertTrue(candidate_path.exists())
            self.assertIn("## 为什么被抓到", candidate_path.read_text(encoding="utf-8"))
            self.assertTrue(comparison_path.exists())
            self.assertTrue(workflow_path.exists())
            self.assertTrue(draft_path.exists())
            self.assertTrue(category_path.exists())
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest tests/test_linuxdo_knowledge.py -q
```

Expected: failure because `session.py` does not exist.

- [ ] **Step 3: Implement session ingestion**

Create `tools/linuxdo_knowledge/session.py`:

```python
from __future__ import annotations

from typing import Any

from .config import KnowledgeConfig
from .obsidian import append_log, page_path_for, scaffold_vault, write_page
from .state import append_evidence, load_hot_indexes, now_iso, save_hot_index, upsert_topic_summary


def ingest_session(
    config: KnowledgeConfig,
    task: dict[str, Any],
    readings: dict[str, Any],
    batch_id: str,
    observed_at: str | None = None,
) -> dict[str, int]:
    observed = observed_at or now_iso()
    scaffold_vault(config)
    indexes = load_hot_indexes(config)
    topic_index = indexes["topic_index"]
    update_state = indexes["topic_update_state"]
    resource_index = indexes["resource_index"]
    claim_index = indexes["claim_index"]
    read_items = readings.get("readings", []) if isinstance(readings, dict) else []
    for reading in read_items:
        if not isinstance(reading, dict):
            continue
        _ingest_reading(config, reading, observed, topic_index, update_state, resource_index, claim_index)
    save_hot_index(config, "topic_index", topic_index)
    save_hot_index(config, "topic_update_state", update_state)
    save_hot_index(config, "resource_index", resource_index)
    save_hot_index(config, "claim_index", claim_index)
    _write_session_report(config, batch_id, observed, task, read_items)
    append_log(config, f"- {observed}: 写入 batch {batch_id}，阅读 {len(read_items)} 帖。")
    return {"readings": len(read_items)}


def _ingest_reading(
    config: KnowledgeConfig,
    reading: dict[str, Any],
    observed_at: str,
    topic_index: dict[str, Any],
    update_state: dict[str, Any],
    resource_index: dict[str, Any],
    claim_index: dict[str, Any],
) -> None:
    topic_id = int(reading.get("topic_id") or reading.get("id"))
    topic_key = str(topic_id)
    topic_index.setdefault("topics", {})[topic_key] = {
        "topic_id": topic_id,
        "title": reading.get("title", ""),
        "url": reading.get("url", ""),
        "value_level": reading.get("value_level", "unknown"),
        "tags": reading.get("tags", []),
        "status": reading.get("status", "active"),
        "watchlist": bool(reading.get("watchlist", False)),
        "last_seen_at": observed_at,
        "resource_ids": [item.get("id") for item in reading.get("resources", []) if isinstance(item, dict) and item.get("id")],
        "claim_ids": [item.get("id") for item in reading.get("claims", []) if isinstance(item, dict) and item.get("id")],
    }
    update_state.setdefault("topics", {})[topic_key] = {
        "topic_id": topic_id,
        "read_reply_count": int(reading.get("reply_count", 0) or 0),
        "last_activity_at": reading.get("last_activity_at", ""),
        "last_read_at": observed_at,
        "last_reading_level": reading.get("reading_level", 1),
        "watchlist": bool(reading.get("watchlist", False)),
        "has_unresolved_dispute": bool(reading.get("has_unresolved_dispute", False)),
    }
    upsert_topic_summary(
        config,
        topic_id,
        {
            "title": reading.get("title", ""),
            "url": reading.get("url", ""),
            "summary": reading.get("summary", ""),
            "key_replies": reading.get("key_replies", []),
            "resources": reading.get("resources", []),
            "claims": reading.get("claims", []),
        },
    )
    for resource in reading.get("resources", []) or []:
        if isinstance(resource, dict) and resource.get("id"):
            resource_index.setdefault("resources", {})[resource["id"]] = {**resource, "last_seen_at": observed_at}
            _write_resource_or_candidate(config, resource, reading, observed_at)
    for claim in reading.get("claims", []) or []:
        if isinstance(claim, dict) and claim.get("id"):
            claim_index.setdefault("claims", {})[claim["id"]] = {**claim, "last_seen_at": observed_at}
    _write_related_pages(config, reading, observed_at)
    for evidence in reading.get("evidence", []) or []:
        if isinstance(evidence, dict):
            append_evidence(
                config,
                {
                    **evidence,
                    "source_type": "linuxdo_topic",
                    "source_url": reading.get("url", ""),
                    "topic_id": topic_id,
                    "impact": {"resources": topic_index["topics"][topic_key]["resource_ids"], "claims": topic_index["topics"][topic_key]["claim_ids"]},
                },
                observed_at=observed_at,
            )


def _write_related_pages(config: KnowledgeConfig, reading: dict[str, Any], observed_at: str) -> None:
    for item in reading.get("comparisons", []) or []:
        if isinstance(item, dict) and item.get("id"):
            _write_structured_page(
                config,
                page_type="comparison",
                item=item,
                observed_at=observed_at,
                sections={
                    "当前结论": item.get("summary", ""),
                    "评价维度": item.get("dimensions", ""),
                    "热门选择": item.get("popular_choices", ""),
                    "潜力选择": item.get("potential_choices", ""),
                    "分歧与争议": item.get("disputes", ""),
                    "适用场景": item.get("use_cases", ""),
                    "相关资源": item.get("resources", ""),
                    "来源证据": f"- {reading.get('url', '')}",
                },
            )
    for item in reading.get("workflows", []) or []:
        if isinstance(item, dict) and item.get("id"):
            _write_structured_page(
                config,
                page_type="workflow",
                item=item,
                observed_at=observed_at,
                sections={"Agent 摘要": item.get("summary", ""), "相关资源": item.get("resources", ""), "来源证据": f"- {reading.get('url', '')}"},
            )
    for item in reading.get("knowledge_drafts", []) or []:
        if isinstance(item, dict) and item.get("id"):
            _write_structured_page(
                config,
                page_type="draft",
                item=item,
                observed_at=observed_at,
                sections={
                    "核心观点": item.get("summary", ""),
                    "方法": item.get("method", ""),
                    "适用场景": item.get("use_cases", ""),
                    "限制与反例": item.get("limits", ""),
                    "来源证据": f"- {reading.get('url', '')}",
                },
            )
    for item in reading.get("categories", []) or []:
        if isinstance(item, dict) and item.get("id"):
            _write_structured_page(
                config,
                page_type="category",
                item=item,
                observed_at=observed_at,
                sections={"资源索引": "\n".join(f"- {value}" for value in item.get("items", [])), "来源证据": f"- {reading.get('url', '')}"},
            )


def _write_structured_page(
    config: KnowledgeConfig,
    page_type: str,
    item: dict[str, Any],
    observed_at: str,
    sections: dict[str, str],
) -> None:
    write_page(
        page_path_for(config, page_type, str(item.get("name") or item.get("id"))),
        frontmatter={
            "id": item["id"],
            "type": page_type,
            "status": item.get("status", "draft" if page_type == "draft" else "active"),
            "tags": [f"catalog/{page_type}" if page_type in {"comparison", "workflow", "category"} else f"wiki/{page_type}"],
            "last_verified": observed_at[:10],
            "evidence_status": item.get("evidence_status", "open_question"),
            "staleness_risk": item.get("staleness_risk", "medium"),
            "watchlist": bool(item.get("watchlist", False)),
        },
        title=str(item.get("name") or item["id"]),
        sections=sections,
    )


def _write_resource_or_candidate(config: KnowledgeConfig, resource: dict[str, Any], reading: dict[str, Any], observed_at: str) -> None:
    page_type = "resource" if resource.get("status") == "active" else "candidate"
    page_path = page_path_for(config, page_type, str(resource.get("name") or resource.get("id")))
    if page_type == "candidate":
        sections = {
            "为什么被抓到": resource.get("capture_reason", reading.get("summary", "")),
            "初步判断": resource.get("summary", reading.get("summary", "")),
            "缺失证据": resource.get("missing_evidence", "需要更多实测、维护状态或对比证据。"),
            "下一步验证": resource.get("next_verification", "再次遇到相关讨论或 GitHub 验证自然触及时再更新。"),
            "来源证据": f"- {reading.get('url', '')}",
        }
    else:
        sections = {
            "Agent 摘要": resource.get("summary", reading.get("summary", "")),
            "解决什么问题": resource.get("problem", ""),
            "适用场景": resource.get("use_cases", ""),
            "社区评价": resource.get("community_view", ""),
            "相关对比": resource.get("comparison", ""),
            "来源证据": f"- {reading.get('url', '')}",
        }
    write_page(
        page_path,
        frontmatter={
            "id": resource["id"],
            "type": page_type,
            "status": resource.get("status", "candidate"),
            "tags": [f"catalog/{page_type}"],
            "last_verified": observed_at[:10],
            "evidence_status": resource.get("evidence_status", "open_question"),
            "staleness_risk": resource.get("staleness_risk", "medium"),
            "watchlist": bool(resource.get("watchlist", False)),
        },
        title=str(resource.get("name") or resource["id"]),
        sections=sections,
    )


def _write_session_report(config: KnowledgeConfig, batch_id: str, observed_at: str, task: dict[str, Any], readings: list[dict[str, Any]]) -> None:
    title = f"{observed_at[:10]} Batch {batch_id}"
    path = config.obsidian_vault_path / "inbox" / "sessions" / f"{observed_at[:10]}-batch-{batch_id}.md"
    new_findings = "\n".join(f"- {item.get('title', '')}: {item.get('summary', '')}" for item in readings)
    skipped = "\n".join(
        f"- {item.get('title', '')}: {item.get('skip_reason', '')}"
        for item in task.get("items", [])
        if isinstance(item, dict) and item.get("skip_reason")
    )
    write_page(
        path,
        frontmatter={"id": f"session:{observed_at[:10]}-batch-{batch_id}", "type": "session", "status": "active", "tags": ["session"]},
        title=title,
        sections={
            "本批范围": f"{len(task.get('items', []))} 个候选，{len(readings)} 个阅读结果。",
            "新发现": new_findings,
            "候选资源": "",
            "资源更新": "",
            "对比/争议": "",
            "只记录为证据的内容": "",
            "跳过与原因": skipped,
            "下一批建议": "",
        },
    )
```

- [ ] **Step 4: Add CLI command**

Modify `tools/linuxdo_surf.py`.

Add import:

```python
from tools.linuxdo_knowledge.session import ingest_session
```

Add function:

```python
def run_knowledge_session(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    task = json.loads(args.task.read_text(encoding="utf-8"))
    readings = json.loads(args.readings.read_text(encoding="utf-8"))
    result = ingest_session(config, task=task, readings=readings, batch_id=args.batch_id)
    write_json(args.output, result)
    return 0
```

Add parser:

```python
    knowledge_session = subparsers.add_parser("knowledge-session", help="写入一批冲浪结果到机器状态和 Obsidian。")
    knowledge_session.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    knowledge_session.add_argument("--task", type=Path, required=True)
    knowledge_session.add_argument("--readings", type=Path, required=True)
    knowledge_session.add_argument("--batch-id", default="001")
    knowledge_session.add_argument("--output", type=Path, default=Path("output/linuxdo_surf/knowledge_session_result.json"))
    knowledge_session.set_defaults(func=run_knowledge_session)
```

- [ ] **Step 5: Run tests**

Run:

```bash
python3 -m unittest tests/test_linuxdo_surf.py tests/test_linuxdo_knowledge.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add tools/linuxdo_surf.py tools/linuxdo_knowledge/session.py tests/test_linuxdo_knowledge.py
git commit -m "feat: ingest knowledge surfing sessions"
```

---

### Task 7: Sync Obsidian Feedback Back Into Machine State

**Files:**
- Create: `tools/linuxdo_knowledge/feedback.py`
- Modify: `tools/linuxdo_surf.py`
- Modify: `tests/test_linuxdo_knowledge.py`

- [ ] **Step 1: Write failing tests for feedback sync**

Append to `tests/test_linuxdo_knowledge.py`:

```python
class FeedbackSyncTests(unittest.TestCase):
    def test_feedback_sync_reads_changed_pages_and_updates_user_feedback(self):
        from tools.linuxdo_knowledge.config import KnowledgeConfig
        from tools.linuxdo_knowledge.feedback import sync_feedback
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, load_hot_indexes

        with TemporaryDirectoryPath() as tmp_path:
            config = KnowledgeConfig(
                project_root=tmp_path,
                state_root=tmp_path / "state" / "knowledge",
                obsidian_vault_path=tmp_path / "vault",
                bookmark_path=None,
                fallback_bookmark_path=None,
                chrome_context_enabled=True,
                github_verification_enabled=True,
            )
            ensure_knowledge_state(config)
            page = config.obsidian_vault_path / "catalog" / "resources" / "Tool.md"
            page.parent.mkdir(parents=True)
            page.write_text(
                "---\nid: resource:tool\ntype: resource\nstatus: deprioritized\n---\n# Tool\n\n## Agent 摘要\n旧\n\n## 我的反馈\n不想继续看这个方向\n",
                encoding="utf-8",
            )

            result = sync_feedback(config, synced_at="2026-06-01T12:00:00")
            indexes = load_hot_indexes(config)

            self.assertEqual(result["changed_files"], 1)
            self.assertEqual(indexes["user_feedback"]["items"][0]["id"], "resource:tool")
            self.assertEqual(indexes["user_feedback"]["items"][0]["feedback"], "不想继续看这个方向")
            self.assertEqual(indexes["resource_index"]["resources"]["resource:tool"]["status"], "deprioritized")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest tests/test_linuxdo_knowledge.py -q
```

Expected: failure because feedback sync does not exist.

- [ ] **Step 3: Implement feedback sync**

Create `tools/linuxdo_knowledge/feedback.py`:

```python
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .config import KnowledgeConfig
from .state import load_hot_indexes, now_iso, save_hot_index


FEEDBACK_HEADING = "## 我的反馈"


def sync_feedback(config: KnowledgeConfig, synced_at: str | None = None) -> dict[str, int]:
    synced = synced_at or now_iso()
    indexes = load_hot_indexes(config)
    sync_state = indexes["feedback_sync_state"]
    known_files = sync_state.setdefault("files", {})
    feedback_state = indexes["user_feedback"]
    resource_index = indexes["resource_index"]
    claim_index = indexes["claim_index"]
    changed = 0
    for path in _markdown_files(config.obsidian_vault_path):
        stat = path.stat()
        key = str(path)
        previous_mtime = known_files.get(key, {}).get("mtime")
        if previous_mtime is not None and float(previous_mtime) >= stat.st_mtime:
            continue
        parsed = parse_markdown_page(path)
        if parsed.get("id"):
            _record_feedback(feedback_state, parsed, path, synced)
            _record_status(resource_index, claim_index, parsed)
        known_files[key] = {"mtime": stat.st_mtime, "last_synced_at": synced}
        changed += 1
    sync_state["last_sync_at"] = synced
    save_hot_index(config, "feedback_sync_state", sync_state)
    save_hot_index(config, "user_feedback", feedback_state)
    save_hot_index(config, "resource_index", resource_index)
    save_hot_index(config, "claim_index", claim_index)
    return {"changed_files": changed}


def parse_markdown_page(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    frontmatter = _parse_frontmatter(text)
    feedback = ""
    if FEEDBACK_HEADING in text:
        feedback = text.split(FEEDBACK_HEADING, 1)[1].strip()
    title_match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    return {
        "path": str(path),
        "title": title_match.group(1).strip() if title_match else path.stem,
        "feedback": feedback,
        **frontmatter,
    }


def _markdown_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.md") if path.is_file())


def _parse_frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    result: dict[str, Any] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip().strip('"')
    return result


def _record_feedback(feedback_state: dict[str, Any], parsed: dict[str, Any], path: Path, synced_at: str) -> None:
    items = feedback_state.setdefault("items", [])
    item_id = parsed.get("id")
    existing = next((item for item in items if item.get("id") == item_id), None)
    payload = {
        "id": item_id,
        "type": parsed.get("type", ""),
        "title": parsed.get("title", ""),
        "path": str(path),
        "feedback": parsed.get("feedback", ""),
        "status": parsed.get("status", ""),
        "synced_at": synced_at,
    }
    if existing:
        existing.update(payload)
    else:
        items.append(payload)


def _record_status(resource_index: dict[str, Any], claim_index: dict[str, Any], parsed: dict[str, Any]) -> None:
    item_id = str(parsed.get("id", ""))
    if item_id.startswith("resource:") or item_id.startswith("candidate:"):
        resource_index.setdefault("resources", {}).setdefault(item_id, {}).update(
            {"status": parsed.get("status", ""), "last_feedback_path": parsed.get("path", "")}
        )
    if item_id.startswith("claim:"):
        claim_index.setdefault("claims", {}).setdefault(item_id, {}).update(
            {"status": parsed.get("status", ""), "last_feedback_path": parsed.get("path", "")}
        )
```

- [ ] **Step 4: Add CLI command**

Modify `tools/linuxdo_surf.py`.

Add import:

```python
from tools.linuxdo_knowledge.feedback import sync_feedback
```

Add function:

```python
def run_feedback_sync(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    result = sync_feedback(config)
    write_json(args.output, result)
    return 0
```

Add parser:

```python
    feedback_sync = subparsers.add_parser("feedback-sync", help="同步 Obsidian 人工反馈到机器状态。")
    feedback_sync.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    feedback_sync.add_argument("--output", type=Path, default=Path("output/linuxdo_surf/feedback_sync_result.json"))
    feedback_sync.set_defaults(func=run_feedback_sync)
```

- [ ] **Step 5: Run tests**

Run:

```bash
python3 -m unittest tests/test_linuxdo_surf.py tests/test_linuxdo_knowledge.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add tools/linuxdo_surf.py tools/linuxdo_knowledge/feedback.py tests/test_linuxdo_knowledge.py
git commit -m "feat: sync obsidian feedback"
```

---

### Task 8: Add State Maintenance And Archive Compaction

**Files:**
- Modify: `tools/linuxdo_knowledge/state.py`
- Modify: `tools/linuxdo_surf.py`
- Modify: `tests/test_linuxdo_knowledge.py`

- [ ] **Step 1: Write failing tests for maintenance**

Append to `tests/test_linuxdo_knowledge.py`:

```python
class StateMaintenanceTests(unittest.TestCase):
    def test_maintenance_deprioritizes_repeated_low_value_topics_without_loading_legacy_history(self):
        from tools.linuxdo_knowledge.config import KnowledgeConfig
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, load_hot_indexes, maintain_state, save_hot_index

        with TemporaryDirectoryPath() as tmp_path:
            config = KnowledgeConfig(
                project_root=tmp_path,
                state_root=tmp_path / "state" / "knowledge",
                obsidian_vault_path=tmp_path / "vault",
                bookmark_path=None,
                fallback_bookmark_path=None,
                chrome_context_enabled=True,
                github_verification_enabled=True,
            )
            ensure_knowledge_state(config)
            (config.state_root / "readings_all.json").write_text("{not valid json", encoding="utf-8")
            save_hot_index(
                config,
                "topic_index",
                {
                    "topics": {
                        "1": {
                            "topic_id": 1,
                            "title": "低价值列表",
                            "status": "active",
                            "skip_count": 3,
                            "skip_reason": "纯列表收集，没有实测",
                        }
                    }
                },
            )

            result = maintain_state(config, maintained_at="2026-06-01T12:00:00")
            indexes = load_hot_indexes(config)
            archive_page = config.obsidian_vault_path / "catalog" / "archive" / "低价值列表.md"

            self.assertEqual(result["deprioritized_topics"], 1)
            self.assertEqual(indexes["topic_index"]["topics"]["1"]["status"], "deprioritized")
            self.assertTrue((config.state_root / "archive" / "maintenance-2026-06-01.jsonl").exists())
            self.assertTrue(archive_page.exists())
            self.assertIn("纯列表收集", archive_page.read_text(encoding="utf-8"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m unittest tests/test_linuxdo_knowledge.py -q
```

Expected: failure because `maintain_state` does not exist.

- [ ] **Step 3: Implement maintenance**

Append to `tools/linuxdo_knowledge/state.py`:

```python
def maintain_state(config: KnowledgeConfig, maintained_at: str | None = None) -> dict[str, int]:
    from .obsidian import page_path_for, scaffold_vault, write_page

    maintained = maintained_at or now_iso()
    scaffold_vault(config)
    indexes = load_hot_indexes(config)
    topic_index = indexes["topic_index"]
    changed = 0
    archive_path = ensure_knowledge_state(config).archive / f"maintenance-{maintained[:10]}.jsonl"
    for topic_id, topic in topic_index.get("topics", {}).items():
        if not isinstance(topic, dict):
            continue
        if topic.get("status") == "active" and int(topic.get("skip_count", 0) or 0) >= 3:
            topic["status"] = "deprioritized"
            topic["deprioritized_at"] = maintained
            append_jsonl(
                archive_path,
                {
                    "kind": "topic_deprioritized",
                    "topic_id": topic_id,
                    "title": topic.get("title", ""),
                    "reason": topic.get("skip_reason", ""),
                    "maintained_at": maintained,
                },
            )
            write_page(
                page_path_for(config, "archive", str(topic.get("title") or topic_id)),
                frontmatter={
                    "id": f"archive:topic-{topic_id}",
                    "type": "archive",
                    "status": "archived",
                    "tags": ["catalog/archive"],
                    "last_verified": maintained[:10],
                    "evidence_status": "stale",
                    "staleness_risk": "high",
                    "watchlist": False,
                },
                title=str(topic.get("title") or topic_id),
                sections={
                    "归档原因": topic.get("skip_reason", ""),
                    "来源证据": topic.get("url", ""),
                },
            )
            changed += 1
    save_hot_index(config, "topic_index", topic_index)
    return {"deprioritized_topics": changed}
```

- [ ] **Step 4: Add CLI command**

Modify `tools/linuxdo_surf.py`.

Add import:

```python
from tools.linuxdo_knowledge.state import maintain_state
```

If `ensure_knowledge_state` is already imported from the same module, combine imports:

```python
from tools.linuxdo_knowledge.state import ensure_knowledge_state, maintain_state
```

Add function:

```python
def run_knowledge_maintain(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    result = maintain_state(config)
    write_json(args.output, result)
    return 0
```

Add parser:

```python
    knowledge_maintain = subparsers.add_parser("knowledge-maintain", help="轻量维护热索引和冷归档。")
    knowledge_maintain.add_argument("--config", type=Path, default=Path("config/knowledge_sources.json"))
    knowledge_maintain.add_argument("--output", type=Path, default=Path("output/linuxdo_surf/knowledge_maintain_result.json"))
    knowledge_maintain.set_defaults(func=run_knowledge_maintain)
```

- [ ] **Step 5: Run tests**

Run:

```bash
python3 -m unittest tests/test_linuxdo_surf.py tests/test_linuxdo_knowledge.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add tools/linuxdo_surf.py tools/linuxdo_knowledge/state.py tests/test_linuxdo_knowledge.py
git commit -m "feat: compact knowledge state"
```

---

### Task 9: Document Workflow And Verify Plan Against Spec

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-06-01-linuxdo-obsidian-knowledge-vault.md`

- [ ] **Step 1: Write README usage**

Replace the empty `README.md` with:

```markdown
# Linux.do Surfing Assistant

本仓库保存 Linux.do 冲浪助手的本地脚本、状态设计和 Obsidian 知识库写入流程。

## 第一版知识库流程

1. 准备配置：

```bash
cp config/knowledge_sources.example.json config/knowledge_sources.json
```

把 `obsidian_vault_path` 和 `linuxdo_scripts_bookmarks.path` 改成本机路径。配置文件不能保存 WebDAV 密码、token 或账号凭证。

2. 初始化机器状态和 vault 结构：

```bash
python3 tools/linuxdo_surf.py knowledge-init --config config/knowledge_sources.json
```

3. 每次冲浪 goal 启动前同步 Obsidian 人工反馈：

```bash
python3 tools/linuxdo_surf.py feedback-sync --config config/knowledge_sources.json
```

4. 同步 LinuxDo Scripts 收藏入口：

```bash
python3 tools/linuxdo_surf.py bookmark-sync --config config/knowledge_sources.json
```

5. 生成一批 20 帖阅读任务：

```bash
python3 tools/linuxdo_surf.py knowledge-plan --config config/knowledge_sources.json --batch-size 20
```

6. Codex 读完后，把结构化阅读结果写入状态和 Obsidian：

```bash
python3 tools/linuxdo_surf.py knowledge-session --config config/knowledge_sources.json --task output/linuxdo_surf/knowledge_task_latest.json --readings output/linuxdo_surf/knowledge_readings.json --batch-id 001
```

7. 每 5-10 批或用户要求时做轻量维护：

```bash
python3 tools/linuxdo_surf.py knowledge-maintain --config config/knowledge_sources.json
```

## 状态原则

- 默认只加载 `state/knowledge/` 里的热索引。
- `readings_all.json` 是旧冷历史，普通启动不读取。
- 已读 topic 更新时只读对应 `topic_summaries/<topic_id>.json`。
- Obsidian 是人工阅读和反馈层，不是机器状态镜像。
- `## 我的反馈` 永远由人维护，脚本写页时保留原文。
```

- [ ] **Step 2: Run full tests**

Run:

```bash
python3 -m unittest tests/test_linuxdo_surf.py tests/test_linuxdo_knowledge.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Run CLI smoke test in a temporary config**

Run:

```bash
tmpdir="$(mktemp -d)"
cat > "$tmpdir/knowledge_sources.json" <<JSON
{
  "obsidian_vault_path": "$tmpdir/vault",
  "state_root": "$tmpdir/state/knowledge",
  "linuxdo_scripts_bookmarks": {
    "enabled": true,
    "path": "$tmpdir/bookmarks.json",
    "fallback_download_path": "$tmpdir/bookmarkData.json"
  }
}
JSON
cat > "$tmpdir/bookmarks.json" <<JSON
[
  {
    "name": "AI Coding / Workflow",
    "list": [
      {
        "title": "Codex workflow",
        "url": "https://linux.do/t/topic/123",
        "tags": ["workflow", "待验证"]
      }
    ]
  }
]
JSON
python3 tools/linuxdo_surf.py knowledge-init --config "$tmpdir/knowledge_sources.json"
python3 tools/linuxdo_surf.py bookmark-sync --config "$tmpdir/knowledge_sources.json" --output "$tmpdir/bookmark_sync_result.json"
python3 tools/linuxdo_surf.py knowledge-plan --config "$tmpdir/knowledge_sources.json" --output "$tmpdir/knowledge_task_latest.json"
test -f "$tmpdir/state/knowledge/topic_index.json"
test -f "$tmpdir/bookmark_sync_result.json"
test -f "$tmpdir/knowledge_task_latest.json"
```

Expected: command exits with status `0` and all `test -f` checks pass.

- [ ] **Step 4: Self-review spec coverage**

Open the approved spec:

```bash
sed -n '1,220p' docs/superpowers/specs/2026-06-01-linuxdo-obsidian-knowledge-vault-design.md
sed -n '220,520p' docs/superpowers/specs/2026-06-01-linuxdo-obsidian-knowledge-vault-design.md
sed -n '520,820p' docs/superpowers/specs/2026-06-01-linuxdo-obsidian-knowledge-vault-design.md
sed -n '820,1095p' docs/superpowers/specs/2026-06-01-linuxdo-obsidian-knowledge-vault-design.md
```

Confirm these mappings in the implementation:

- Machine/Obsidian split: `state.py`, `obsidian.py`, `README.md`.
- LinuxDo Scripts bookmark JSON: `bookmarks.py`, `bookmark-sync`.
- Lightweight hot indexes and cold history: `state.py`, tests with invalid `readings_all.json`.
- Topic reading levels and render-on-demand policy: `strategy.py`, `knowledge-plan`.
- Batch one-write flow: `session.py`, `knowledge-session`.
- Feedback sync: `feedback.py`, `feedback-sync`.
- Watchlist without scheduled polling: `strategy.py` only reacts to encountered frontier items.
- Obsidian templates and feedback preservation: `obsidian.py`.
- Maintenance and archive compaction: `maintain_state`, `knowledge-maintain`.

- [ ] **Step 5: Commit docs and final cleanup**

Run:

```bash
git status --short
git add README.md docs/superpowers/plans/2026-06-01-linuxdo-obsidian-knowledge-vault.md
git commit -m "docs: document knowledge vault workflow"
```

Expected: commit succeeds. If implementation tasks already committed the plan file, this commit may include only `README.md`.

---

## Execution Order

Run the tasks in order. Each task produces a working increment and a commit:

1. Config and empty state skeleton.
2. Hot index and cold history operations.
3. LinuxDo Scripts bookmark diff.
4. Token-efficient reading task planner.
5. Obsidian scaffold and feedback-preserving page writes.
6. Batch session ingestion and one-write Obsidian update.
7. Obsidian feedback sync.
8. Lightweight maintenance and archive compaction.
9. README, smoke test, and spec coverage review.

## Final Verification

Before declaring implementation complete, run:

```bash
python3 -m unittest tests/test_linuxdo_surf.py tests/test_linuxdo_knowledge.py -q
git status --short
```

Expected:

- All tests pass.
- `git status --short` shows no uncommitted implementation changes.
- No normal command reads or parses `state/knowledge/readings_all.json`.
- Obsidian page rewrites preserve `## 我的反馈`.
- `knowledge-plan` produces a batch task from hot indexes and frontier queue only.
- `knowledge-session` writes one session report per batch.
