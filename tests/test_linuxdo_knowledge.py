import importlib.util
import json
import subprocess
import sys
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
    def knowledge_config(self, tmp_path):
        from tools.linuxdo_knowledge.config import KnowledgeConfig

        return KnowledgeConfig(
            project_root=tmp_path,
            state_root=tmp_path / "state" / "knowledge",
            obsidian_vault_path=tmp_path / "vault",
            bookmark_path=tmp_path / "bookmarks.json",
            fallback_bookmark_path=tmp_path / "bookmarkData.json",
            chrome_context_enabled=True,
            github_verification_enabled=True,
        )

    def test_load_config_rejects_secret_like_credentials_anywhere(self):
        from tools.linuxdo_knowledge.config import load_config

        forbidden_keys = [
            "webdav_password",
            "webdav_token",
            "webdav_username",
            "webdav_account",
            "password",
            "token",
        ]

        with TemporaryDirectoryPath() as tmp_path:
            for key in forbidden_keys:
                config_path = tmp_path / f"{key}.json"
                config_path.write_text(
                    json.dumps(
                        {
                            "obsidian_vault_path": str(tmp_path / "vault"),
                            "nested": [{"source": {key: "must-not-be-here"}}],
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )

                with self.subTest(key=key):
                    with self.assertRaisesRegex(ValueError, "WebDAV"):
                        load_config(config_path)

    def test_load_config_rejects_string_booleans_and_ignores_blank_optional_paths(self):
        from tools.linuxdo_knowledge.config import load_config

        with TemporaryDirectoryPath() as tmp_path:
            config_path = tmp_path / "knowledge_sources.json"
            config_path.write_text(
                json.dumps(
                    {
                        "linuxdo_scripts_bookmarks": {
                            "path": "   ",
                            "fallback_download_path": "\t",
                        },
                        "chrome_context": {"enabled": "false"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "chrome_context.enabled"):
                load_config(config_path)

            config_path.write_text(
                json.dumps(
                    {
                        "linuxdo_scripts_bookmarks": {
                            "path": "   ",
                            "fallback_download_path": "\t",
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertIsNone(config.bookmark_path)
        self.assertIsNone(config.fallback_bookmark_path)

    def test_load_config_stores_bookmark_enabled_flag(self):
        from tools.linuxdo_knowledge.config import load_config

        with TemporaryDirectoryPath() as tmp_path:
            config_path = tmp_path / "knowledge_sources.json"
            config_path.write_text(
                json.dumps({"linuxdo_scripts_bookmarks": {"enabled": False}}, ensure_ascii=False),
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertFalse(config.bookmark_enabled)

    def test_ensure_knowledge_state_creates_hot_indexes_and_directories(self):
        from tools.linuxdo_knowledge.state import ensure_knowledge_state

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)

            ensure_knowledge_state(config)

            state_root = tmp_path / "state" / "knowledge"
            expected_json = {
                "topic_index.json": {"topics": {}},
                "topic_update_state.json": {"topics": {}},
                "resource_index.json": {"resources": {}},
                "claim_index.json": {"claims": {}},
                "feedback_sync_state.json": {"last_sync_at": None, "files": {}},
                "user_feedback.json": {"items": []},
                "frontier_queue.json": {"items": []},
                "bookmark_source_index.json": {"bookmarks": {}},
            }
            for filename, expected in expected_json.items():
                with self.subTest(filename=filename):
                    self.assertEqual(json.loads((state_root / filename).read_text(encoding="utf-8")), expected)

            self.assertEqual((state_root / "session_log.jsonl").read_text(encoding="utf-8"), "")
            self.assertTrue((state_root / "topic_summaries").is_dir())
            self.assertTrue((state_root / "evidence_shards").is_dir())
            self.assertTrue((state_root / "archive").is_dir())

    def test_load_hot_indexes_ignores_corrupt_cold_history(self):
        from tools.linuxdo_knowledge.state import load_hot_indexes

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            cold_history = config.state_root / "readings_all.json"
            cold_history.parent.mkdir(parents=True)
            cold_history.write_text("{invalid json", encoding="utf-8")

            indexes = load_hot_indexes(config)

        self.assertEqual(
            indexes,
            {
                "topic_index": {"topics": {}},
                "topic_update_state": {"topics": {}},
                "resource_index": {"resources": {}},
                "claim_index": {"claims": {}},
                "feedback_sync_state": {"last_sync_at": None, "files": {}},
                "user_feedback": {"items": []},
                "frontier_queue": {"items": []},
                "bookmark_source_index": {"bookmarks": {}},
            },
        )

    def test_save_hot_index_writes_known_index_and_rejects_unknown_name(self):
        from tools.linuxdo_knowledge.state import save_hot_index

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            path = save_hot_index(config, "topic_index", {"topics": {"7": {"title": "known"}}})

            with self.assertRaisesRegex(ValueError, "unknown hot index"):
                save_hot_index(config, "readings_all", {})

            data = json.loads(path.read_text(encoding="utf-8"))
            cold_history_exists = (config.state_root / "readings_all.json").exists()

        self.assertEqual(path, config.state_root / "topic_index.json")
        self.assertEqual(data, {"topics": {"7": {"title": "known"}}})
        self.assertFalse(cold_history_exists)

    def test_upsert_topic_summary_merges_fields_and_updates_timestamp(self):
        from tools.linuxdo_knowledge.state import topic_summary_path, upsert_topic_summary

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            path = topic_summary_path(config, "42")
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps(
                    {
                        "topic_id": 42,
                        "title": "old title",
                        "kept": "yes",
                        "updated_at": "2026-01-01T00:00:00+00:00",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            written_path = upsert_topic_summary(config, "42", {"title": "new title", "tags": ["ai"]})

            data = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(written_path, path)
        self.assertEqual(data["topic_id"], 42)
        self.assertEqual(data["title"], "new title")
        self.assertEqual(data["kept"], "yes")
        self.assertEqual(data["tags"], ["ai"])
        self.assertNotEqual(data["updated_at"], "2026-01-01T00:00:00+00:00")

    def test_append_evidence_writes_observed_month_jsonl(self):
        from tools.linuxdo_knowledge.state import append_evidence

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            written_path = append_evidence(
                config,
                {"topic_id": 7, "claim": "useful"},
                observed_at="2026-05-12T08:09:10+00:00",
            )
            line = written_path.read_text(encoding="utf-8").strip()
            item = json.loads(line)

        self.assertEqual(written_path, config.state_root / "evidence_shards" / "2026-05.jsonl")
        self.assertEqual(item, {"topic_id": 7, "claim": "useful", "observed_at": "2026-05-12T08:09:10+00:00"})

    def test_append_evidence_rejects_invalid_observed_at_without_weird_shard(self):
        from tools.linuxdo_knowledge.state import append_evidence

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)

            with self.assertRaisesRegex(ValueError, "observed_at"):
                append_evidence(config, {"topic_id": 7}, observed_at="../../bad")

            shard_paths = list((config.state_root / "evidence_shards").glob("*.jsonl"))

        self.assertEqual(shard_paths, [])

    def test_append_evidence_appends_multiple_lines_for_same_month(self):
        from tools.linuxdo_knowledge.state import append_evidence

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            first_path = append_evidence(config, {"topic_id": 1}, observed_at="2026-05-01T00:00:00+00:00")
            second_path = append_evidence(config, {"topic_id": 2}, observed_at="2026-05-31T23:59:59+00:00")
            lines = first_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(first_path, second_path)
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0])["topic_id"], 1)
        self.assertEqual(json.loads(lines[1])["topic_id"], 2)

    def test_cli_knowledge_init_uses_config_and_creates_state(self):
        with TemporaryDirectoryPath() as tmp_path:
            config_path = tmp_path / "config" / "knowledge_sources.json"
            config_path.parent.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "obsidian_vault_path": "vault",
                        "linuxdo_scripts_bookmarks": {
                            "enabled": True,
                            "path": "bookmarks.json",
                            "fallback_download_path": "bookmarkData.json",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            exit_code = linuxdo_surf.main(["knowledge-init", "--config", str(config_path)])

            self.assertEqual(exit_code, 0)
            self.assertTrue((tmp_path / "state" / "knowledge" / "topic_index.json").exists())
            self.assertTrue((tmp_path / "state" / "knowledge" / "session_log.jsonl").exists())

    def test_script_knowledge_init_uses_config_and_creates_state(self):
        with TemporaryDirectoryPath() as tmp_path:
            config_path = tmp_path / "config" / "knowledge_sources.json"
            config_path.parent.mkdir()
            config_path.write_text(
                json.dumps({"obsidian_vault_path": "vault"}, ensure_ascii=False),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SURF_PATH),
                    "knowledge-init",
                    "--config",
                    str(config_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((tmp_path / "state" / "knowledge" / "topic_index.json").exists())


class BookmarkSyncTests(unittest.TestCase):
    def knowledge_config(self, tmp_path, *, bookmark_path=None, fallback_bookmark_path=None, bookmark_enabled=True):
        from tools.linuxdo_knowledge.config import KnowledgeConfig

        return KnowledgeConfig(
            project_root=tmp_path,
            state_root=tmp_path / "state" / "knowledge",
            obsidian_vault_path=tmp_path / "vault",
            bookmark_path=bookmark_path if bookmark_path is not None else tmp_path / "bookmarks.json",
            fallback_bookmark_path=fallback_bookmark_path
            if fallback_bookmark_path is not None
            else tmp_path / "bookmarkData.json",
            chrome_context_enabled=True,
            github_verification_enabled=True,
            bookmark_enabled=bookmark_enabled,
        )

    def bookmark_export(self, *, title="某 skill 讨论", tags=None, cate="开发调优", folder="Skills / Plugins"):
        return [
            {
                "id": 0,
                "name": folder,
                "list": [
                    {
                        "cate": cate,
                        "tags": ["skill", "实测"] if tags is None else tags,
                        "timestamp": 1780151443336,
                        "title": title,
                        "url": "https://linux.do/t/topic/2273499",
                    }
                ],
            }
        ]

    def write_bookmarks(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_parse_bookmark_export_flattens_linuxdo_scripts_shape(self):
        from tools.linuxdo_knowledge.bookmarks import parse_bookmark_export

        items = parse_bookmark_export(self.bookmark_export())

        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["folder"], "Skills / Plugins")
        self.assertEqual(item["cate"], "开发调优")
        self.assertEqual(item["tags"], ["skill", "实测"])
        self.assertEqual(item["timestamp"], 1780151443336)
        self.assertEqual(item["title"], "某 skill 讨论")
        self.assertEqual(item["url"], "https://linux.do/t/topic/2273499")
        self.assertEqual(item["topic_id"], 2273499)
        self.assertRegex(item["content_hash"], r"^[0-9a-f]{64}$")

    def test_extract_topic_id_accepts_topic_and_slug_urls(self):
        from tools.linuxdo_knowledge.bookmarks import extract_topic_id

        self.assertEqual(extract_topic_id("https://linux.do/t/topic/2273499"), 2273499)
        self.assertEqual(extract_topic_id("https://linux.do/t/some-slug/2273499"), 2273499)
        self.assertIsNone(extract_topic_id("https://linux.do/u/someone"))

    def test_sync_bookmarks_adds_new_bookmark_to_index_and_frontier(self):
        from tools.linuxdo_knowledge.bookmarks import sync_bookmarks

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            self.write_bookmarks(config.bookmark_path, self.bookmark_export())

            counts = sync_bookmarks(config, seen_at="2026-06-01T00:00:00+00:00")

            bookmark_index = json.loads((config.state_root / "bookmark_source_index.json").read_text(encoding="utf-8"))
            frontier = json.loads((config.state_root / "frontier_queue.json").read_text(encoding="utf-8"))

        self.assertEqual(counts, {"new": 1, "metadata_changed": 0, "unchanged": 0})
        bookmark = bookmark_index["bookmarks"]["https://linux.do/t/topic/2273499"]
        self.assertEqual(bookmark["title"], "某 skill 讨论")
        self.assertEqual(bookmark["last_seen_at"], "2026-06-01T00:00:00+00:00")
        self.assertEqual(len(frontier["items"]), 1)
        self.assertEqual(frontier["items"][0]["source"], "linuxdo_scripts_bookmark")
        self.assertEqual(frontier["items"][0]["topic_id"], 2273499)
        self.assertEqual(frontier["items"][0]["folder"], "Skills / Plugins")
        self.assertEqual(frontier["items"][0]["tags"], ["skill", "实测"])

    def test_sync_bookmarks_reuses_existing_frontier_item_when_bookmark_index_is_missing(self):
        from tools.linuxdo_knowledge.bookmarks import sync_bookmarks
        from tools.linuxdo_knowledge.state import ensure_knowledge_state

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            self.write_bookmarks(config.bookmark_path, self.bookmark_export())
            ensure_knowledge_state(config)
            (config.state_root / "frontier_queue.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "url": "https://linux.do/t/topic/2273499",
                                "title": "旧 frontier 标题",
                                "source": "manual",
                                "created_at": "2026-05-31T00:00:00+00:00",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (config.state_root / "bookmark_source_index.json").write_text(
                json.dumps({"bookmarks": {}}, ensure_ascii=False),
                encoding="utf-8",
            )

            counts = sync_bookmarks(config, seen_at="2026-06-01T00:00:00+00:00")

            bookmark_index = json.loads((config.state_root / "bookmark_source_index.json").read_text(encoding="utf-8"))
            frontier = json.loads((config.state_root / "frontier_queue.json").read_text(encoding="utf-8"))

        self.assertEqual(counts, {"new": 1, "metadata_changed": 0, "unchanged": 0})
        self.assertIn("https://linux.do/t/topic/2273499", bookmark_index["bookmarks"])
        self.assertEqual(len(frontier["items"]), 1)
        self.assertEqual(frontier["items"][0]["title"], "某 skill 讨论")
        self.assertEqual(frontier["items"][0]["created_at"], "2026-05-31T00:00:00+00:00")

    def test_sync_bookmarks_unchanged_updates_last_seen_without_duplicate_frontier_item(self):
        from tools.linuxdo_knowledge.bookmarks import sync_bookmarks

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            self.write_bookmarks(config.bookmark_path, self.bookmark_export())
            sync_bookmarks(config, seen_at="2026-06-01T00:00:00+00:00")

            counts = sync_bookmarks(config, seen_at="2026-06-02T00:00:00+00:00")

            bookmark_index = json.loads((config.state_root / "bookmark_source_index.json").read_text(encoding="utf-8"))
            frontier = json.loads((config.state_root / "frontier_queue.json").read_text(encoding="utf-8"))

        self.assertEqual(counts, {"new": 0, "metadata_changed": 0, "unchanged": 1})
        self.assertEqual(bookmark_index["bookmarks"]["https://linux.do/t/topic/2273499"]["last_seen_at"], "2026-06-02T00:00:00+00:00")
        self.assertEqual(len(frontier["items"]), 1)

    def test_sync_bookmarks_metadata_change_updates_index_and_bumps_frontier_item(self):
        from tools.linuxdo_knowledge.bookmarks import sync_bookmarks

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            self.write_bookmarks(config.bookmark_path, self.bookmark_export())
            sync_bookmarks(config, seen_at="2026-06-01T00:00:00+00:00")
            self.write_bookmarks(
                config.bookmark_path,
                self.bookmark_export(title="更新后的 skill 讨论", tags=["plugin"], cate="工具评测", folder="Inbox"),
            )

            counts = sync_bookmarks(config, seen_at="2026-06-03T00:00:00+00:00")

            bookmark_index = json.loads((config.state_root / "bookmark_source_index.json").read_text(encoding="utf-8"))
            frontier = json.loads((config.state_root / "frontier_queue.json").read_text(encoding="utf-8"))

        self.assertEqual(counts, {"new": 0, "metadata_changed": 1, "unchanged": 0})
        bookmark = bookmark_index["bookmarks"]["https://linux.do/t/topic/2273499"]
        self.assertEqual(bookmark["title"], "更新后的 skill 讨论")
        self.assertEqual(bookmark["folder"], "Inbox")
        self.assertEqual(len(frontier["items"]), 1)
        self.assertEqual(frontier["items"][0]["title"], "更新后的 skill 讨论")
        self.assertEqual(frontier["items"][0]["folder"], "Inbox")
        self.assertEqual(frontier["items"][0]["tags"], ["plugin"])
        self.assertEqual(frontier["items"][0]["updated_at"], "2026-06-03T00:00:00+00:00")

    def test_sync_bookmarks_disabled_returns_zeros_and_does_not_read_file(self):
        from tools.linuxdo_knowledge.bookmarks import sync_bookmarks

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(
                tmp_path,
                bookmark_path=tmp_path / "invalid.json",
                fallback_bookmark_path=None,
                bookmark_enabled=False,
            )
            config.bookmark_path.write_text("{not json", encoding="utf-8")

            counts = sync_bookmarks(config, seen_at="2026-06-01T00:00:00+00:00")

        self.assertEqual(counts, {"new": 0, "metadata_changed": 0, "unchanged": 0})

    def test_sync_bookmarks_uses_fallback_when_configured_path_is_missing(self):
        from tools.linuxdo_knowledge.bookmarks import sync_bookmarks

        with TemporaryDirectoryPath() as tmp_path:
            fallback_path = tmp_path / "downloads" / "bookmarkData.json"
            config = self.knowledge_config(
                tmp_path,
                bookmark_path=tmp_path / "missing.json",
                fallback_bookmark_path=fallback_path,
            )
            self.write_bookmarks(fallback_path, self.bookmark_export())

            counts = sync_bookmarks(config, seen_at="2026-06-01T00:00:00+00:00")

            frontier = json.loads((config.state_root / "frontier_queue.json").read_text(encoding="utf-8"))

        self.assertEqual(counts, {"new": 1, "metadata_changed": 0, "unchanged": 0})
        self.assertEqual(frontier["items"][0]["url"], "https://linux.do/t/topic/2273499")


class ReadingStrategyTests(unittest.TestCase):
    def knowledge_config(self, tmp_path):
        from tools.linuxdo_knowledge.config import KnowledgeConfig

        return KnowledgeConfig(
            project_root=tmp_path,
            state_root=tmp_path / "state" / "knowledge",
            obsidian_vault_path=tmp_path / "vault",
            bookmark_path=None,
            fallback_bookmark_path=None,
            chrome_context_enabled=True,
            github_verification_enabled=True,
        )

    def write_hot_index(self, config, name, data):
        path = config.state_root / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_decide_reading_plan_skips_unchanged_read_topic(self):
        from tools.linuxdo_knowledge.strategy import decide_reading_plan

        plan = decide_reading_plan(
            {"title": "Codex 工作流", "reply_count": 10, "last_activity_at": "2026-06-01T10:00:00+00:00"},
            {"read_reply_count": 10, "last_activity_at": "2026-06-01T10:00:00+00:00"},
        )

        self.assertEqual(plan["level"], 0)
        self.assertEqual(plan["action"], "skip")
        self.assertIn("unchanged", plan["skip_reason"])

    def test_decide_reading_plan_watchlist_new_replies_reads_incremental_level_2(self):
        from tools.linuxdo_knowledge.strategy import decide_reading_plan

        plan = decide_reading_plan(
            {"title": "Codex 工作流更新", "reply_count": 12, "last_activity_at": "2026-06-02T10:00:00+00:00"},
            {"read_reply_count": 10, "last_activity_at": "2026-06-01T10:00:00+00:00", "watchlist": True},
        )

        self.assertEqual(plan["level"], 2)
        self.assertEqual(plan["action"], "read_incremental")
        self.assertEqual(plan["skip_reason"], "")

    def test_decide_reading_plan_high_signal_words_upgrade_to_level_2(self):
        from tools.linuxdo_knowledge.strategy import decide_reading_plan

        signal_titles = ["实测某工具", "踩坑记录", "替代方案", "不推荐使用", "更新了", "解决了报错", "对比结果", "争议讨论"]

        for title in signal_titles:
            with self.subTest(title=title):
                plan = decide_reading_plan({"title": title, "reply_count": 1})
                self.assertEqual(plan["level"], 2)
                self.assertEqual(plan["action"], "read")

    def test_decide_reading_plan_low_value_terms_can_metadata_only(self):
        from tools.linuxdo_knowledge.strategy import decide_reading_plan

        plan = decide_reading_plan({"title": "今日签到水贴闲聊", "reply_count": 0})

        self.assertEqual(plan["level"], 0)
        self.assertEqual(plan["action"], "metadata_only")
        self.assertIn("low_value", plan["skip_reason"])

    def test_decide_reading_plan_requires_render_for_visual_ui_signals(self):
        from tools.linuxdo_knowledge.strategy import decide_reading_plan

        signal_text = "如图 看图 截图 效果如下 UI WebUI 按钮 报错图"
        plan = decide_reading_plan({"title": "界面问题", "first_text": signal_text})

        self.assertTrue(plan["render_required"])

    def test_build_knowledge_task_uses_hot_indexes_sorts_and_ignores_corrupt_cold_history(self):
        from tools.linuxdo_knowledge.strategy import build_knowledge_task

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            (config.state_root / "readings_all.json").parent.mkdir(parents=True)
            (config.state_root / "readings_all.json").write_text("{not valid json", encoding="utf-8")
            self.write_hot_index(
                config,
                "frontier_queue",
                {
                    "items": [
                        {
                            "url": "https://linux.do/t/topic/9",
                            "title": "Z topic",
                            "priority": 20,
                            "reply_count": 1,
                            "suggested_level": 1,
                        },
                        {
                            "url": "https://linux.do/t/topic/8",
                            "title": "A topic",
                            "priority": 90,
                            "reply_count": 2,
                            "suggested_level": 1,
                        },
                        {
                            "url": "https://linux.do/t/topic/7",
                            "title": "B topic",
                            "priority": 90,
                            "reply_count": 3,
                            "suggested_level": 2,
                        },
                    ]
                },
            )

            task = build_knowledge_task(config, batch_size=2, created_at="2026-06-01T12:00:00+00:00")

        self.assertEqual(task["created_at"], "2026-06-01T12:00:00+00:00")
        self.assertEqual(task["source"], "knowledge_frontier_queue")
        self.assertEqual(task["extraction_policy"], "dom_text_first_render_on_demand")
        self.assertEqual(task["history_policy"], "load_hot_indexes_only")
        self.assertEqual([item["topic_id"] for item in task["items"]], [8, 7])
        self.assertEqual([item["title"] for item in task["items"]], ["A topic", "B topic"])
        self.assertEqual(task["items"][0]["reading_level"], 1)
        for key in [
            "topic_id",
            "title",
            "url",
            "reading_level",
            "action",
            "skip_reason",
            "render_required",
            "render_policy",
            "reply_policy",
        ]:
            self.assertIn(key, task["items"][0])

    def test_build_knowledge_task_uses_topic_update_state_for_skip_and_incremental(self):
        from tools.linuxdo_knowledge.strategy import build_knowledge_task

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            self.write_hot_index(
                config,
                "frontier_queue",
                {
                    "items": [
                        {
                            "topic_id": 1,
                            "url": "https://linux.do/t/topic/1",
                            "title": "已读帖",
                            "priority": 80,
                            "reply_count": 5,
                            "last_activity_at": "2026-06-01T10:00:00+00:00",
                        },
                        {
                            "topic_id": 2,
                            "url": "https://linux.do/t/topic/2",
                            "title": "关注帖",
                            "priority": 70,
                            "reply_count": 8,
                            "last_activity_at": "2026-06-02T10:00:00+00:00",
                        },
                    ]
                },
            )
            self.write_hot_index(
                config,
                "topic_update_state",
                {
                    "topics": {
                        "1": {"read_reply_count": 5, "last_activity_at": "2026-06-01T10:00:00+00:00"},
                        "2": {
                            "read_reply_count": 6,
                            "last_activity_at": "2026-06-01T10:00:00+00:00",
                            "watchlist": True,
                        },
                    }
                },
            )

            task = build_knowledge_task(config, batch_size=20, created_at="2026-06-01T12:00:00+00:00")

        self.assertEqual(task["items"][0]["reading_level"], 0)
        self.assertEqual(task["items"][0]["action"], "skip")
        self.assertIn("unchanged", task["items"][0]["skip_reason"])
        self.assertEqual(task["items"][1]["reading_level"], 2)
        self.assertEqual(task["items"][1]["action"], "read_incremental")
