import importlib.util
import json
import re
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


GENERATOR_RESIDUE_RE = re.compile(
    r"## 来源证据|legacy_summary|\bBatch\b|\bbatch\b|旧帖|旧记录|旧冲浪|本批|第\s*[0-9]+\s*批"
)


def assert_no_generator_residue(testcase, text, *, page_name="generated"):
    from tools.linuxdo_knowledge.quality import lint_human_markdown

    issues = lint_human_markdown(text, page_name=page_name)
    testcase.assertEqual([], issues, page_name)
    testcase.assertNotRegex(text, GENERATOR_RESIDUE_RE, page_name)


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
                "evidence_index.json": {"evidence": {}},
                "evidence_by_claim.json": {"claims": {}},
                "evidence_by_resource.json": {"resources": {}},
                "counter_evidence_queue.json": {"items": []},
                "feedback_sync_state.json": {"last_sync_at": None, "files": {}},
                "user_feedback.json": {"items": []},
                "frontier_queue.json": {"items": []},
                "bookmark_source_index.json": {"bookmarks": {}},
            }
            for filename, expected in expected_json.items():
                with self.subTest(filename=filename):
                    self.assertEqual(json.loads((state_root / filename).read_text(encoding="utf-8")), expected)

            self.assertEqual((state_root / "session_log.jsonl").read_text(encoding="utf-8"), "")
            self.assertEqual((state_root / "claim_events.jsonl").read_text(encoding="utf-8"), "")
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
                "evidence_index": {"evidence": {}},
                "evidence_by_claim": {"claims": {}},
                "evidence_by_resource": {"resources": {}},
                "counter_evidence_queue": {"items": []},
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

    def test_rebuild_evidence_edges_materializes_history_and_deduplicates_ids(self):
        from tools.linuxdo_knowledge.evidence_rebuild import rebuild_evidence_edges
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, load_hot_indexes, save_hot_index

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            ensure_knowledge_state(config)
            save_hot_index(config, "claim_index", {"claims": {"claim:tool": {"id": "claim:tool"}}})
            save_hot_index(config, "resource_index", {"resources": {"resource:tool": {"id": "resource:tool"}}})
            save_hot_index(
                config,
                "evidence_index",
                {
                    "evidence": {
                        "evidence:dup": {
                            "id": "evidence:dup",
                            "payload_variant_review_decision": "same_claim_updated_summary",
                            "payload_variant_review_reason": "同一 claim 的摘要更新，保留最新物化。",
                            "payload_variant_reviewed_at": "2026-06-07T11:00:00+00:00",
                        }
                    }
                },
            )
            save_hot_index(
                config,
                "counter_evidence_queue",
                {
                    "items": [
                        {
                            "id": "counter:claim:tool:evidence:dup",
                            "status": "reviewed",
                            "review_status": "reviewed",
                            "review_decision": "already_reflected",
                            "review_reason": "claim 已包含反方边界。",
                            "reviewed_at": "2026-06-07T11:00:00+00:00",
                        }
                    ]
                },
            )
            shard = config.state_root / "evidence_shards" / "2026-06.jsonl"
            shard.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "id": "evidence:dup",
                                "source_id": "source:linuxdo:1",
                                "topic_id": 1,
                                "source_url": "https://linux.do/t/topic/1",
                                "summary": "旧支持证据",
                                "stance": "supports",
                                "claim_ids": ["claim:tool"],
                                "resource_ids": ["resource:tool"],
                                "observed_at": "2026-06-01T10:00:00+00:00",
                            },
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            {
                                "id": "evidence:dup",
                                "source_id": "source:linuxdo:1",
                                "topic_id": 1,
                                "source_url": "https://linux.do/t/topic/1",
                                "summary": "新失败反馈",
                                "stance": "reports_failure",
                                "confidence": "high",
                                "claim_refs": ["claim:tool"],
                                "resource_refs": ["resource:tool"],
                                "observed_at": "2026-06-01T11:00:00+00:00",
                            },
                            ensure_ascii=False,
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = rebuild_evidence_edges(config, rebuilt_at="2026-06-07T12:00:00+00:00")
            indexes = load_hot_indexes(config)

        self.assertEqual(result["evidence_lines"], 2)
        self.assertEqual(result["unique_evidence_ids"], 1)
        self.assertEqual(result["duplicate_evidence_ids"], 1)
        self.assertEqual(result["counter_queue_items"], 1)
        self.assertEqual(result["counter_queue_open_items"], 0)
        self.assertEqual(result["counter_queue_reviewed_items"], 1)
        evidence = indexes["evidence_index"]["evidence"]["evidence:dup"]
        self.assertEqual(evidence["summary"], "新失败反馈")
        self.assertEqual(evidence["relation"], "counter")
        self.assertEqual(evidence["seen_count"], 2)
        self.assertEqual(evidence["payload_variant_count"], 2)
        self.assertEqual(len(evidence["payload_hashes"]), 2)
        self.assertEqual(evidence["payload_variant_review_decision"], "same_claim_updated_summary")
        self.assertEqual(evidence["payload_variant_review_reason"], "同一 claim 的摘要更新，保留最新物化。")
        self.assertEqual(evidence["first_seen_at"], "2026-06-01T10:00:00+00:00")
        self.assertEqual(evidence["last_seen_at"], "2026-06-01T11:00:00+00:00")
        self.assertEqual(indexes["evidence_by_claim"]["claims"]["claim:tool"]["counter_evidence_ids"], ["evidence:dup"])
        self.assertEqual(indexes["evidence_by_resource"]["resources"]["resource:tool"]["counter_evidence_ids"], ["evidence:dup"])
        self.assertEqual(indexes["counter_evidence_queue"]["items"][0]["id"], "counter:claim:tool:evidence:dup")
        self.assertEqual(indexes["counter_evidence_queue"]["items"][0]["status"], "reviewed")
        self.assertEqual(indexes["counter_evidence_queue"]["items"][0]["review_decision"], "already_reflected")

    def test_knowledge_lint_reports_actionable_protocol_gaps(self):
        from tools.linuxdo_knowledge.knowledge_lint import lint_knowledge_protocol
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, save_hot_index

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            ensure_knowledge_state(config)
            save_hot_index(
                config,
                "claim_index",
                {
                    "claims": {
                        "claim:conflict": {"id": "claim:conflict", "status": "active"},
                        "claim:stale": {"id": "claim:stale", "status": "needs_retest"},
                        "claim:orphan": {"id": "claim:orphan", "status": "active"},
                    }
                },
            )
            save_hot_index(
                config,
                "resource_index",
                {
                    "resources": {
                        "resource:linked": {"id": "resource:linked", "status": "watching", "evidence_status": "community_evidence"},
                        "resource:gap": {"id": "resource:gap", "status": "candidate", "evidence_status": "needs_source_review"},
                    }
                },
            )
            save_hot_index(
                config,
                "evidence_by_claim",
                {
                    "claims": {
                        "claim:conflict": {
                            "supporting_evidence_ids": ["evidence:support"],
                            "counter_evidence_ids": ["evidence:counter"],
                        },
                        "claim:stale": {"supporting_evidence_ids": ["evidence:old"]},
                    }
                },
            )
            save_hot_index(
                config,
                "evidence_by_resource",
                {"resources": {"resource:linked": {"related_evidence_ids": ["evidence:linked"]}}},
            )
            save_hot_index(
                config,
                "topic_update_state",
                {"topics": {"123": {"topic_id": 123, "metadata_refresh_blocked": True, "metadata_refresh_blocked_reason": "blocked"}}},
            )

            report = lint_knowledge_protocol(config, limit=20)

        self.assertEqual(report["issue_counts"]["contradictions"], 1)
        self.assertEqual(report["issue_counts"]["stale_claims"], 1)
        self.assertEqual(report["issue_counts"]["orphan_claims"], 1)
        self.assertEqual(report["issue_counts"]["orphan_resources"], 1)
        self.assertEqual(report["issue_counts"]["source_gaps"], 1)
        self.assertEqual(report["issue_counts"]["parked"], 1)
        self.assertGreaterEqual(report["summary"]["actionable_count"], 4)
        self.assertIn(
            {"target_type": "claim", "target_id": "claim:conflict", "action": "review_contradiction"},
            report["next_actions"],
        )

    def test_repair_audit_issues_applies_safe_batch_fixes_and_clears_audit_counts(self):
        from tools.linuxdo_knowledge.audit_repair import repair_audit_issues
        from tools.linuxdo_knowledge.index_audit import audit_knowledge_indexes
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, load_hot_indexes, save_hot_index

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            readings_dir = tmp_path / "out"
            readings_dir.mkdir()
            ensure_knowledge_state(config)
            save_hot_index(config, "topic_index", {"topics": {"1": {"topic_id": 1, "title": "旧帖"}}})
            save_hot_index(config, "topic_update_state", {"topics": {"1": {"topic_id": 1}}})
            save_hot_index(
                config,
                "resource_index",
                {
                    "resources": {
                        "collection:demo": {
                            "id": "collection:demo",
                            "evidence_status": "legacy_summary",
                            "category": "",
                        }
                    }
                },
            )
            save_hot_index(
                config,
                "claim_index",
                {"claims": {"claim:demo": {"id": "claim:demo", "evidence_status": "legacy_summary"}}},
            )
            readings_path = readings_dir / "knowledge_readings_surf_001.json"
            readings_path.write_text(
                json.dumps(
                    {"readings": [{"topic_id": 1, "status": "metadata_only", "reading_level": 1}]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            before = audit_knowledge_indexes(config, readings_dir=readings_dir)
            result = repair_audit_issues(
                config,
                readings_dir=readings_dir,
                apply=True,
                limit=10,
                repaired_at="2026-06-07T12:00:00+00:00",
            )
            after = audit_knowledge_indexes(config, readings_dir=readings_dir)
            indexes = load_hot_indexes(config)
            repaired_readings = json.loads(readings_path.read_text(encoding="utf-8"))

        self.assertEqual(before["issue_counts"]["legacy_status"], 2)
        self.assertEqual(before["issue_counts"]["empty_category"], 1)
        self.assertEqual(before["issue_counts"]["topic_update_missing"], 1)
        self.assertEqual(before["issue_counts"]["metadata_refresh_pending"], 0)
        self.assertEqual(before["issue_counts"]["metadata_only_level_mismatch"], 1)
        self.assertEqual(result["legacy_status_repaired"], 2)
        self.assertEqual(result["empty_category_filled"], 1)
        self.assertEqual(result["topic_updates_marked_for_refresh"], 1)
        self.assertEqual(result["metadata_only_levels_fixed"], 1)
        self.assertEqual(after["issue_counts"]["legacy_status"], 0)
        self.assertEqual(after["issue_counts"]["empty_category"], 0)
        self.assertEqual(after["issue_counts"]["topic_update_missing"], 0)
        self.assertEqual(after["issue_counts"]["metadata_refresh_pending"], 1)
        self.assertEqual(after["issue_counts"]["metadata_only_level_mismatch"], 0)
        self.assertEqual(indexes["resource_index"]["resources"]["collection:demo"]["evidence_status"], "needs_source_review")
        self.assertEqual(indexes["resource_index"]["resources"]["collection:demo"]["category"], "collection")
        self.assertEqual(indexes["claim_index"]["claims"]["claim:demo"]["evidence_status"], "needs_source_review")
        self.assertTrue(indexes["topic_update_state"]["topics"]["1"]["metadata_refresh_needed"])
        self.assertEqual(repaired_readings["readings"][0]["reading_level"], 0)

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
            self.assertTrue((tmp_path / "vault" / "00_Home" / "index.md").exists())
            self.assertTrue((tmp_path / "vault" / "90_Inbox" / "sessions").is_dir())

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
            self.assertTrue((tmp_path / "vault" / "00_Home" / "index.md").exists())


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


class ObsidianVaultTests(unittest.TestCase):
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

    def test_scaffold_vault_creates_directories_and_missing_docs(self):
        from tools.linuxdo_knowledge.obsidian import scaffold_vault

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            existing_agents = config.obsidian_vault_path / "AGENTS.md"
            existing_agents.parent.mkdir(parents=True)
            existing_agents.write_text("custom agent rules\n", encoding="utf-8")

            scaffold_vault(config)

            expected_dirs = [
                "00_Home",
                "10_Catalog/resources",
                "10_Catalog/services",
                "10_Catalog/collections",
                "10_Catalog/candidates",
                "10_Catalog/comparisons",
                "10_Catalog/workflows",
                "10_Catalog/categories",
                "10_Catalog/archive",
                "20_Knowledge/concepts",
                "20_Knowledge/components",
                "20_Knowledge/practices",
                "20_Knowledge/claims",
                "20_Knowledge/notes",
                "20_Knowledge/drafts",
                "30_Feedback/preferences",
                "30_Feedback/decisions",
                "30_Feedback/rejections",
                "90_Inbox/review-queue",
                "90_Inbox/sessions",
                "_system/sources/linuxdo",
                "_system/sources/github",
                "_system/evidence/linuxdo",
                "_system/evidence/github",
            ]
            for relative_path in expected_dirs:
                with self.subTest(relative_path=relative_path):
                    self.assertTrue((config.obsidian_vault_path / relative_path).is_dir())

            self.assertTrue((config.obsidian_vault_path / "CLAUDE.md").is_file())
            self.assertTrue((config.obsidian_vault_path / "00_Home" / "index.md").is_file())
            self.assertTrue((config.obsidian_vault_path / "00_Home" / "log.md").is_file())
            self.assertEqual(existing_agents.read_text(encoding="utf-8"), "custom agent rules\n")

            claude_text = (config.obsidian_vault_path / "CLAUDE.md").read_text(encoding="utf-8")

        self.assertIn("knowledge rules", claude_text)
        self.assertIn("## 我的反馈", claude_text)
        self.assertIn("Preserve", claude_text)

    def test_scaffold_vault_agents_mentions_knowledge_rules_and_feedback(self):
        from tools.linuxdo_knowledge.obsidian import scaffold_vault

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)

            scaffold_vault(config)

            agents_text = (config.obsidian_vault_path / "AGENTS.md").read_text(encoding="utf-8")

        self.assertIn("knowledge rules", agents_text)
        self.assertIn("## 我的反馈", agents_text)
        self.assertIn("Preserve", agents_text)

    def test_write_page_writes_frontmatter_title_sections_and_feedback_heading(self):
        from tools.linuxdo_knowledge.obsidian import FEEDBACK_HEADING, write_page

        with TemporaryDirectoryPath() as tmp_path:
            path = tmp_path / "vault" / "catalog" / "resources" / "demo.md"

            write_page(
                path,
                {"title": "Demo", "draft": False, "tags": ["ai", "linux.do"], "score": 3},
                "Demo",
                [("摘要", "这是摘要。"), ("链接", "- https://linux.do/t/topic/1")],
            )

            text = path.read_text(encoding="utf-8")

        self.assertTrue(text.startswith("---\n"))
        self.assertIn("title: Demo\n", text)
        self.assertIn("draft: false\n", text)
        self.assertIn("tags:\n  - ai\n  - linux.do\n", text)
        self.assertIn("score: 3\n", text)
        self.assertIn("# Demo\n", text)
        self.assertIn("## 摘要\n\n这是摘要。\n", text)
        self.assertIn("## 链接\n\n- https://linux.do/t/topic/1\n", text)
        self.assertIn(f"{FEEDBACK_HEADING}\n", text)

    def test_write_page_preserves_existing_feedback_when_rewriting_agent_sections(self):
        from tools.linuxdo_knowledge.obsidian import FEEDBACK_HEADING, write_page

        with TemporaryDirectoryPath() as tmp_path:
            path = tmp_path / "vault" / "wiki" / "notes" / "demo.md"
            write_page(path, {"title": "Old"}, "Old", [("旧摘要", "旧内容")])
            feedback_after_heading = "\n\n用户第一行\n- 保留这个列表\n\n"
            path.write_text(path.read_text(encoding="utf-8") + "\n用户第一行\n- 保留这个列表\n\n", encoding="utf-8")

            write_page(path, {"title": "New"}, "New", [("新摘要", "新内容")])

            text = path.read_text(encoding="utf-8")
            preserved_feedback = text.split(FEEDBACK_HEADING, 1)[1]

        self.assertIn("# New\n", text)
        self.assertIn("## 新摘要\n\n新内容\n", text)
        self.assertNotIn("旧摘要", text)
        self.assertEqual(preserved_feedback, feedback_after_heading)

    def test_write_page_preserves_feedback_spacing_at_end(self):
        from tools.linuxdo_knowledge.obsidian import FEEDBACK_HEADING, write_page

        with TemporaryDirectoryPath() as tmp_path:
            path = tmp_path / "vault" / "wiki" / "notes" / "demo.md"
            path.parent.mkdir(parents=True)
            path.write_text(
                "---\ntitle: Old\n---\n\n# Old\n\n## 旧摘要\n\n旧内容\n\n## 我的反馈\n\n第一行\n\n第二段\n",
                encoding="utf-8",
            )

            write_page(path, {"title": "New"}, "New", [("新摘要", "新内容")])

            text = path.read_text(encoding="utf-8")

        self.assertNotIn("旧摘要", text)
        self.assertTrue(text.endswith(f"{FEEDBACK_HEADING}\n\n第一行\n\n第二段\n"))

    def test_write_page_does_not_treat_inline_feedback_heading_as_feedback_section(self):
        from tools.linuxdo_knowledge.obsidian import FEEDBACK_HEADING, write_page

        with TemporaryDirectoryPath() as tmp_path:
            path = tmp_path / "vault" / "wiki" / "notes" / "guide.md"
            write_page(
                path,
                {"type": "guide"},
                "Guide",
                [("说明", "正文里提到 `## 我的反馈` 这个标题，但这不是反馈区。")],
            )

            write_page(path, {"type": "guide"}, "Guide", [("新说明", "新正文")])
            text = path.read_text(encoding="utf-8")

        self.assertIn("## 新说明", text)
        self.assertIn(f"{FEEDBACK_HEADING}\n", text)
        self.assertNotIn("正文里提到", text)

    def test_page_path_for_maps_types_and_safe_filename_removes_invalid_characters(self):
        from tools.linuxdo_knowledge.obsidian import page_path_for, safe_filename

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)

            cases = {
                "resource": "10_Catalog/resources",
                "service": "10_Catalog/services",
                "collection": "10_Catalog/collections",
                "candidate": "10_Catalog/candidates",
                "comparison": "10_Catalog/comparisons",
                "workflow": "10_Catalog/workflows",
                "category": "10_Catalog/categories",
                "archive": "10_Catalog/archive",
                "concept": "20_Knowledge/concepts",
                "component": "20_Knowledge/components",
                "practice": "20_Knowledge/practices",
                "claim": "20_Knowledge/claims",
                "draft": "20_Knowledge/drafts",
                "note": "20_Knowledge/notes",
                "session": "90_Inbox/sessions",
                "linuxdo_source": "_system/sources/linuxdo",
                "linuxdo_evidence": "_system/evidence/linuxdo",
            }
            for page_type, directory in cases.items():
                with self.subTest(page_type=page_type):
                    path = page_path_for(config, page_type, " Bad / Name:* ?<>|  ")
                    self.assertEqual(path, config.obsidian_vault_path / directory / "Bad-Name.md")

        self.assertEqual(safe_filename(" a\t b \n c "), "a-b-c")
        self.assertEqual(safe_filename(":/\\*?\"<>|"), "untitled")

    def test_append_log_appends_without_destroying_existing_log(self):
        from tools.linuxdo_knowledge.obsidian import append_log

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            log_path = config.obsidian_vault_path / "00_Home" / "log.md"
            log_path.parent.mkdir(parents=True)
            log_path.write_text("first\n", encoding="utf-8")

            append_log(config, "second")
            append_log(config, "third")

            text = log_path.read_text(encoding="utf-8")

        self.assertEqual(text, "first\nsecond\nthird\n")


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

        self.assertEqual([item["topic_id"] for item in task["items"]], [2, 1])
        self.assertEqual(task["items"][0]["reading_level"], 2)
        self.assertEqual(task["items"][0]["action"], "read_incremental")
        self.assertIn("unread_replies", task["items"][0]["refresh_triggers"])
        self.assertEqual(task["items"][1]["reading_level"], 1)
        self.assertEqual(task["items"][1]["action"], "refresh_light")
        self.assertIn("rediscovered", task["items"][1]["refresh_triggers"])

    def test_build_knowledge_task_prioritizes_watchlist_topic_with_unread_replies(self):
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
                        "2151853": {
                            "topic_id": 2151853,
                            "title": "Superpowers 讨论",
                            "url": "https://linux.do/t/topic/2151853",
                            "reply_count": 56,
                            "read_reply_count": 32,
                            "watchlist": True,
                            "related_resources": ["superpowers"],
                        }
                    }
                },
            )
            save_hot_index(
                config,
                "frontier_queue",
                {"items": [{"topic_id": 9, "title": "普通新帖", "priority": 100, "reply_count": 1}]},
            )

            task = build_knowledge_task(config, batch_size=2, created_at="2026-06-05T12:00:00+08:00")

        self.assertEqual(task["items"][0]["topic_id"], 2151853)
        self.assertEqual(task["items"][0]["reading_level"], 2)
        self.assertEqual(task["items"][0]["action"], "read_incremental")
        self.assertEqual(task["items"][0]["refresh_mode"], "lightweight")
        self.assertIn("watchlist", task["items"][0]["refresh_triggers"])
        self.assertIn("unread_replies", task["items"][0]["refresh_triggers"])
        self.assertIn("unread replies", task["items"][0]["reason"])

    def test_build_knowledge_task_refreshes_feedback_and_rediscovered_old_topic_first(self):
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, save_hot_index
        from tools.linuxdo_knowledge.strategy import build_knowledge_task

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            ensure_knowledge_state(config)
            save_hot_index(
                config,
                "topic_index",
                {
                    "topics": {
                        "100": {
                            "topic_id": 100,
                            "title": "Superpowers 旧讨论",
                            "url": "https://linux.do/t/topic/100",
                            "resource_ids": ["resource:superpowers"],
                            "claim_ids": ["claim:context-budget"],
                        }
                    }
                },
            )
            save_hot_index(
                config,
                "topic_update_state",
                {"topics": {"100": {"topic_id": 100, "reply_count": 12, "read_reply_count": 12}}},
            )
            save_hot_index(
                config,
                "user_feedback",
                {
                    "items": [
                        {"id": "resource:superpowers", "feedback": "继续关注轻量流程"},
                        {"id": "claim:context-budget", "feedback": "需要复查上下文成本"},
                    ]
                },
            )
            save_hot_index(
                config,
                "frontier_queue",
                {
                    "items": [
                        {"topic_id": 200, "title": "高优先级新帖", "priority": 100, "reply_count": 1},
                        {"topic_id": 100, "title": "Superpowers 再次被发现", "priority": 1, "reply_count": 12},
                    ]
                },
            )

            task = build_knowledge_task(config, batch_size=2, created_at="2026-06-05T12:00:00+08:00")

        self.assertEqual([item["topic_id"] for item in task["items"]], [100, 200])
        self.assertEqual(task["items"][0]["reading_level"], 1)
        self.assertEqual(task["items"][0]["action"], "refresh_light")
        self.assertEqual(task["items"][0]["refresh_mode"], "lightweight")
        self.assertIn("human_feedback", task["items"][0]["refresh_triggers"])
        self.assertIn("rediscovered", task["items"][0]["refresh_triggers"])
        self.assertIn("human feedback", task["items"][0]["reason"])
        self.assertIn("rediscovered", task["items"][0]["reason"])

    def test_build_knowledge_task_ignores_feedback_already_covered_by_later_read(self):
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, save_hot_index
        from tools.linuxdo_knowledge.strategy import build_knowledge_task

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            ensure_knowledge_state(config)
            save_hot_index(
                config,
                "topic_index",
                {
                    "topics": {
                        "100": {
                            "topic_id": 100,
                            "title": "Superpowers 旧讨论",
                            "url": "https://linux.do/t/topic/100",
                            "resource_ids": ["resource:superpowers"],
                        }
                    }
                },
            )
            save_hot_index(
                config,
                "topic_update_state",
                {
                    "topics": {
                        "100": {
                            "topic_id": 100,
                            "reply_count": 12,
                            "read_reply_count": 12,
                            "last_read_at": "2026-06-06T12:00:00+08:00",
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
                            "id": "resource:superpowers",
                            "feedback": "继续关注轻量流程",
                            "synced_at": "2026-06-05T12:00:00+08:00",
                        }
                    ]
                },
            )

            task = build_knowledge_task(config, batch_size=2, created_at="2026-06-07T12:00:00+08:00")

        self.assertEqual(task["items"], [])

    def test_build_knowledge_task_ignores_unsynced_feedback_after_topic_read(self):
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, save_hot_index
        from tools.linuxdo_knowledge.strategy import build_knowledge_task

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            ensure_knowledge_state(config)
            save_hot_index(
                config,
                "topic_index",
                {
                    "topics": {
                        "100": {
                            "topic_id": 100,
                            "title": "Superpowers 旧讨论",
                            "url": "https://linux.do/t/topic/100",
                            "resource_ids": ["resource:superpowers"],
                        }
                    }
                },
            )
            save_hot_index(
                config,
                "topic_update_state",
                {
                    "topics": {
                        "100": {
                            "topic_id": 100,
                            "reply_count": 12,
                            "read_reply_count": 12,
                            "last_read_at": "2026-06-06T12:00:00+08:00",
                        }
                    }
                },
            )
            save_hot_index(
                config,
                "user_feedback",
                {"items": [{"id": "resource:superpowers", "feedback": "继续关注轻量流程"}]},
            )

            task = build_knowledge_task(config, batch_size=2, created_at="2026-06-07T12:00:00+08:00")

        self.assertEqual(task["items"], [])

    def test_build_knowledge_task_does_not_refresh_empty_watchlist_feedback(self):
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, save_hot_index
        from tools.linuxdo_knowledge.strategy import build_knowledge_task

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            ensure_knowledge_state(config)
            save_hot_index(
                config,
                "topic_index",
                {
                    "topics": {
                        "100": {
                            "topic_id": 100,
                            "title": "Anyrouter 旧讨论",
                            "url": "https://linux.do/t/topic/100",
                            "resource_ids": ["resource:anyrouter"],
                            "watchlist": True,
                        }
                    }
                },
            )
            save_hot_index(
                config,
                "topic_update_state",
                {
                    "topics": {
                        "100": {
                            "topic_id": 100,
                            "reply_count": 12,
                            "read_reply_count": 12,
                            "last_read_at": "2026-06-06T12:00:00+08:00",
                            "watchlist": True,
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
                            "id": "resource:anyrouter",
                            "feedback": "",
                            "status": "watching",
                            "watchlist": True,
                            "synced_at": "2026-06-07T12:00:00+08:00",
                        }
                    ]
                },
            )

            task = build_knowledge_task(config, batch_size=2, created_at="2026-06-07T12:30:00+08:00")

        self.assertEqual(task["items"], [])

    def test_build_knowledge_task_skips_deprioritized_and_archived_topics(self):
        from tools.linuxdo_knowledge.strategy import build_knowledge_task

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            self.write_hot_index(
                config,
                "frontier_queue",
                {
                    "items": [
                        {"topic_id": 1, "title": "降权帖", "priority": 100},
                        {"topic_id": 2, "title": "归档帖", "priority": 90},
                        {"topic_id": 3, "title": "可读帖", "priority": 80},
                    ]
                },
            )
            self.write_hot_index(
                config,
                "topic_index",
                {
                    "topics": {
                        "1": {"topic_id": 1, "status": "deprioritized"},
                        "2": {"topic_id": 2, "status": "archived"},
                        "3": {"topic_id": 3, "status": "active"},
                    }
                },
            )

            task = build_knowledge_task(config, batch_size=20, created_at="2026-06-01T12:00:00+00:00")

        self.assertEqual([item["topic_id"] for item in task["items"]], [3])

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

    def test_build_knowledge_task_prioritizes_manual_frontier_items(self):
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
                            "title": "Known watchlist topic",
                            "reply_count": 10,
                            "read_reply_count": 10,
                            "watchlist": True,
                        }
                    }
                },
            )
            save_hot_index(
                config,
                "user_feedback",
                {"items": [{"id": "topic:42", "feedback": "继续追"}]},
            )
            save_hot_index(
                config,
                "frontier_queue",
                {
                    "items": [
                        {
                            "topic_id": 123456,
                            "url": "https://linux.do/t/topic/123456",
                            "reason": "手动追踪",
                            "source": "manual",
                            "priority": 80,
                        }
                    ]
                },
            )

            task = build_knowledge_task(config, batch_size=1, created_at="2026-06-06T12:00:00+08:00")

        self.assertEqual(task["items"][0]["topic_id"], 123456)
        self.assertEqual(task["items"][0]["reason"], "手动追踪")

    def test_disputed_claim_related_topic_enters_refresh_candidates(self):
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, save_hot_index
        from tools.linuxdo_knowledge.strategy import build_knowledge_task

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
        self.assertGreaterEqual(task["items"][0]["reading_level"], 2)


class SessionIngestionTests(unittest.TestCase):
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

    def test_ingest_session_updates_state_and_writes_obsidian_pages(self):
        from tools.linuxdo_knowledge.session import ingest_session
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, load_hot_indexes

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            ensure_knowledge_state(config)
            task = {
                "created_at": "2026-06-01T12:00:00+00:00",
                "items": [
                    {
                        "topic_id": 123,
                        "title": "Codex workflow",
                        "url": "https://linux.do/t/topic/123?page=0",
                    }
                ],
            }
            readings = {
                "readings": [
                    {
                        "topic_id": 123,
                        "title": "Codex workflow",
                        "url": "https://linux.do/t/topic/123?page=0",
                        "summary": "讨论长任务上下文预算。",
                        "value_level": "high",
                        "tags": ["workflow"],
                        "reply_count": 12,
                        "last_activity_at": "2026-06-01T11:00:00+00:00",
                        "highest_post_number": 18,
                        "highest_post_id": 98765,
                        "read_ranges": [{"from": 1, "to": 18}],
                        "content_fingerprint": "topic-fingerprint-1",
                        "resources": [
                            {
                                "id": "candidate:codex-workflow",
                                "name": "Codex Workflow",
                                "status": "candidate",
                                "capture_reason": "多人讨论上下文预算。",
                                "summary": "这段长摘要不应该进入热索引。" * 20,
                                "evidence": ["长证据不进入热索引"],
                            }
                        ],
                        "claims": [
                            {
                                "id": "claim:context-budget",
                                "text": "长任务需要轻量索引",
                                "summary": "长 claim 解释也不应该进入热索引。" * 20,
                            }
                        ],
                        "evidence": [
                            {
                                "summary": "回复支持只读新增楼层。",
                                "evidence_status": "supporting",
                            }
                        ],
                        "comparisons": [
                            {
                                "id": "comparison:workflow-tools",
                                "name": "Workflow Tools",
                                "summary": "按 token 成本和反馈闭环比较。",
                            }
                        ],
                        "workflows": [
                            {
                                "id": "workflow:linuxdo-obsidian",
                                "name": "Linux.do Obsidian Workflow",
                                "summary": "冲浪后写入 Obsidian。",
                            }
                        ],
                        "knowledge_drafts": [
                            {
                                "id": "draft:lightweight-index",
                                "name": "轻量索引",
                                "summary": "热索引降低重复读取成本。",
                            }
                        ],
                        "categories": [
                            {
                                "id": "category:skills",
                                "name": "skills",
                                "items": ["Codex Workflow"],
                            }
                        ],
                    }
                ]
            }

            result = ingest_session(
                config,
                task=task,
                readings=readings,
                batch_id="001",
                observed_at="2026-06-01T12:30:00+00:00",
            )
            indexes = load_hot_indexes(config)
            session_path = config.obsidian_vault_path / "90_Inbox" / "sessions" / "2026-06-01-session-001.md"
            candidate_path = config.obsidian_vault_path / "10_Catalog" / "candidates" / "Codex-Workflow.md"
            comparison_path = config.obsidian_vault_path / "10_Catalog" / "comparisons" / "Workflow-Tools.md"
            workflow_path = config.obsidian_vault_path / "10_Catalog" / "workflows" / "Linux.do-Obsidian-Workflow.md"
            draft_path = config.obsidian_vault_path / "20_Knowledge" / "drafts" / "轻量索引.md"
            category_path = config.obsidian_vault_path / "10_Catalog" / "categories" / "skills.md"
            source_path = config.obsidian_vault_path / "_system" / "sources" / "linuxdo" / "linuxdo-topic-123.md"
            evidence_page_path = config.obsidian_vault_path / "_system" / "evidence" / "linuxdo" / "linuxdo-123-evidence-1.md"
            claim_path = config.obsidian_vault_path / "20_Knowledge" / "claims" / "claim-context-budget.md"
            evidence_path = config.state_root / "evidence_shards" / "2026-06.jsonl"
            session_exists = session_path.exists()
            session_text = session_path.read_text(encoding="utf-8") if session_exists else ""
            candidate_exists = candidate_path.exists()
            candidate_text = candidate_path.read_text(encoding="utf-8") if candidate_exists else ""
            comparison_exists = comparison_path.exists()
            comparison_text = comparison_path.read_text(encoding="utf-8") if comparison_exists else ""
            workflow_exists = workflow_path.exists()
            workflow_text = workflow_path.read_text(encoding="utf-8") if workflow_exists else ""
            draft_exists = draft_path.exists()
            category_exists = category_path.exists()
            source_exists = source_path.exists()
            evidence_page_exists = evidence_page_path.exists()
            claim_exists = claim_path.exists()
            evidence_text = evidence_path.read_text(encoding="utf-8") if evidence_path.exists() else ""

        self.assertEqual(result["readings"], 1)
        self.assertIn("123", indexes["topic_index"]["topics"])
        self.assertEqual(indexes["topic_update_state"]["topics"]["123"]["read_reply_count"], 12)
        self.assertEqual(indexes["topic_update_state"]["topics"]["123"]["highest_post_number"], 18)
        self.assertEqual(indexes["topic_update_state"]["topics"]["123"]["highest_post_id"], 98765)
        self.assertEqual(indexes["topic_update_state"]["topics"]["123"]["read_ranges"], [{"from": 1, "to": 18}])
        self.assertEqual(indexes["topic_update_state"]["topics"]["123"]["content_fingerprint"], "topic-fingerprint-1")
        self.assertIn("candidate:codex-workflow", indexes["resource_index"]["resources"])
        self.assertNotIn("summary", indexes["resource_index"]["resources"]["candidate:codex-workflow"])
        self.assertNotIn("evidence", indexes["resource_index"]["resources"]["candidate:codex-workflow"])
        self.assertIn("claim:context-budget", indexes["claim_index"]["claims"])
        self.assertNotIn("summary", indexes["claim_index"]["claims"]["claim:context-budget"])
        self.assertTrue(session_exists)
        self.assertIn("Codex workflow", session_text)
        self.assertTrue(candidate_exists)
        for heading in (
            "## 一句话判断",
            "## 它是什么",
            "## 适合什么",
            "## 不适合什么",
            "## 当前结论",
            "## 关键证据",
            "## 反方与风险",
            "## 相关竞品",
            "## 待验证",
            "## 来源",
        ):
            self.assertIn(heading, candidate_text)
        self.assertNotIn("高相关", candidate_text)
        self.assertNotRegex(candidate_text, r"\.\.\.|…")
        self.assertTrue(comparison_exists)
        self.assertTrue(workflow_exists)
        for heading in (
            "## 当前结论",
            "## 比较范围",
            "## 入口选项",
            "## 各派意见",
            "## 评价维度",
            "## 适合选择",
            "## 不适合选择",
            "## 为什么",
            "## 待验证",
            "## 证据与来源",
        ):
            self.assertIn(heading, comparison_text)
        for heading in (
            "## 一句话判断",
            "## 它是什么",
            "## 适合什么",
            "## 不适合什么",
            "## 当前结论",
            "## 核心步骤",
            "## 关键证据",
            "## 反方与风险",
            "## 相关对比",
            "## 待验证",
            "## 来源",
        ):
            self.assertIn(heading, workflow_text)
        self.assertTrue(draft_exists)
        self.assertTrue(category_exists)
        self.assertTrue(source_exists)
        self.assertTrue(evidence_page_exists)
        self.assertTrue(claim_exists)
        self.assertIn("只读新增楼层", evidence_text)

    def test_ingest_session_generated_human_pages_strip_old_residue(self):
        from tools.linuxdo_knowledge.session import ingest_session

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)

            ingest_session(
                config,
                task={"items": [{"topic_id": 901, "title": "旧帖任务", "skip_reason": "本批已跳过"}]},
                readings={
                    "readings": [
                        {
                            "topic_id": 901,
                            "title": "Demo topic",
                            "url": "https://linux.do/t/topic/901",
                            "summary": "高相关：风佬巨作 v5.0，zcf...",
                            "resources": [
                                {
                                    "id": "candidate:demo-tool",
                                    "name": "Demo Tool",
                                    "status": "candidate",
                                    "summary": "Demo Tool 是候选资源，当前记录显示它被多次提及；是否值得采用要看来源证据、维护状态和反方反馈。",
                                    "capture_reason": "旧记录里高相关。",
                                }
                            ],
                            "comparisons": [
                                {
                                    "id": "comparison:demo-choice",
                                    "name": "Demo Choice",
                                    "summary": "Batch 旧帖里的中等相关摘要...",
                                }
                            ],
                            "workflows": [
                                {
                                    "id": "workflow:demo-flow",
                                    "name": "Demo Flow",
                                    "summary": "旧冲浪记录说它高相关...",
                                }
                            ],
                            "knowledge_drafts": [
                                {
                                    "id": "draft:demo-draft",
                                    "name": "Demo Draft",
                                    "summary": "本批旧摘要...",
                                }
                            ],
                            "categories": [
                                {
                                    "id": "category:demo",
                                    "name": "Demo Category",
                                    "items": ["Demo Tool"],
                                }
                            ],
                        }
                    ]
                },
                batch_id="007",
                observed_at="2026-06-05T12:30:00+08:00",
            )
            generated_pages = [
                (
                    path.relative_to(config.obsidian_vault_path).as_posix(),
                    path.read_text(encoding="utf-8"),
                )
                for path in config.obsidian_vault_path.rglob("*.md")
                if "_system" not in path.relative_to(config.obsidian_vault_path).parts
            ]

        self.assertTrue(generated_pages)
        for relative_path, text in generated_pages:
            with self.subTest(path=relative_path):
                assert_no_generator_residue(self, text, page_name=relative_path)

    def test_knowledge_session_cli_writes_result_file(self):
        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            config_path = tmp_path / "config" / "knowledge_sources.json"
            config_path.parent.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "obsidian_vault_path": str(config.obsidian_vault_path),
                        "state_root": str(config.state_root),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            task_path = tmp_path / "task.json"
            readings_path = tmp_path / "readings.json"
            output_path = tmp_path / "result.json"
            task_path.write_text(json.dumps({"items": []}), encoding="utf-8")
            readings_path.write_text(json.dumps({"readings": []}), encoding="utf-8")

            exit_code = linuxdo_surf.main(
                [
                    "knowledge-session",
                    "--config",
                    str(config_path),
                    "--task",
                    str(task_path),
                    "--readings",
                    str(readings_path),
                    "--batch-id",
                    "002",
                    "--output",
                    str(output_path),
                ]
            )
            result = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(result, {"readings": 0})

    def test_ingest_session_updates_existing_obsidian_page_by_frontmatter_id(self):
        from tools.linuxdo_knowledge.session import ingest_session

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            existing_path = config.obsidian_vault_path / "10_Catalog" / "archive" / "Human-Renamed.md"
            existing_path.parent.mkdir(parents=True)
            existing_path.write_text(
                "---\nid: \"candidate:codex-workflow\"\ntype: candidate\nstatus: candidate\n---\n\n"
                "# Human Renamed\n\n## 旧区块\n\n旧内容\n\n## 我的反馈\n\n人写的反馈\n",
                encoding="utf-8",
            )
            readings = {
                "readings": [
                    {
                        "topic_id": 123,
                        "title": "Codex workflow",
                        "url": "https://linux.do/t/topic/123",
                        "resources": [
                            {
                                "id": "candidate:codex-workflow",
                                "name": "Codex Workflow New Name",
                                "status": "candidate",
                                "capture_reason": "新证据。",
                            }
                        ],
                    }
                ]
            }

            ingest_session(config, task={"items": []}, readings=readings, batch_id="003", observed_at="2026-06-01T12:30:00+00:00")
            existing_text = existing_path.read_text(encoding="utf-8")
            duplicate_path_exists = (config.obsidian_vault_path / "10_Catalog" / "candidates" / "Codex-Workflow-New-Name.md").exists()

        self.assertIn("# Codex Workflow New Name", existing_text)
        self.assertIn("新证据", existing_text)
        self.assertIn("## 我的反馈\n\n人写的反馈\n", existing_text)
        self.assertFalse(duplicate_path_exists)

    def test_ingest_session_writes_supported_resource_to_resources_directory(self):
        from tools.linuxdo_knowledge.session import ingest_session

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            readings = {
                "readings": [
                    {
                        "topic_id": 321,
                        "title": "Tool 讨论",
                        "url": "https://linux.do/t/topic/321",
                        "summary": "讨论 Tool 的实测使用场景。",
                        "resources": [
                            {
                                "id": "resource:tool",
                                "name": "Tool",
                                "status": "watching",
                                "evidence_status": "source_extract",
                                "summary": "有明确来源和场景，适合作为观察资源。",
                                "key_evidence": "帖子中给出实测场景和限制。",
                            }
                        ],
                    }
                ]
            }

            ingest_session(config, task={"items": []}, readings=readings, batch_id="004", observed_at="2026-06-01T12:30:00+00:00")
            resource_path = config.obsidian_vault_path / "10_Catalog" / "resources" / "Tool.md"
            candidate_path = config.obsidian_vault_path / "10_Catalog" / "candidates" / "Tool.md"
            resource_exists = resource_path.exists()
            candidate_exists = candidate_path.exists()
            resource_text = resource_path.read_text(encoding="utf-8") if resource_exists else ""

        self.assertTrue(resource_exists)
        self.assertFalse(candidate_exists)
        self.assertIn("type: resource", resource_text)
        self.assertIn("status: watching", resource_text)

    def test_ingest_session_writes_service_resource_with_service_sections(self):
        from tools.linuxdo_knowledge.session import ingest_session

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            readings = {
                "readings": [
                    {
                        "topic_id": 322,
                        "title": "Anyrouter 讨论",
                        "url": "https://linux.do/t/topic/322",
                        "summary": "讨论 Anyrouter 的 SubAgent 和 Haiku 兼容问题。",
                        "resources": [
                            {
                                "id": "resource:anyrouter",
                                "name": "Anyrouter",
                                "status": "watching",
                                "evidence_status": "source_extract",
                                "summary": "Anyrouter 可用于 Claude Code 路由，但存在兼容风险。",
                                "risks": "SubAgent、Haiku 和 WebSearch 兼容性需要版本级复核。",
                            }
                        ],
                    }
                ]
            }

            ingest_session(config, task={"items": []}, readings=readings, batch_id="005", observed_at="2026-06-01T12:30:00+00:00")
            service_path = config.obsidian_vault_path / "10_Catalog" / "services" / "Anyrouter.md"
            service_exists = service_path.exists()
            service_text = service_path.read_text(encoding="utf-8") if service_exists else ""

        self.assertTrue(service_exists)
        self.assertIn("type: service", service_text)
        for heading in (
            "## 一句话判断",
            "## 它是什么",
            "## 适合什么",
            "## 不适合什么",
            "## 当前结论",
            "## 稳定性",
            "## 隐私/安全风险",
            "## 价格/额度变化风险",
            "## 关键证据",
            "## 反方与风险",
            "## 相关竞品",
            "## 待验证",
            "## 来源",
        ):
            self.assertIn(heading, service_text)

    def test_ingest_session_repairs_preserved_page_missing_required_sections(self):
        from tools.linuxdo_knowledge.session import ingest_session

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            existing_path = config.obsidian_vault_path / "10_Catalog" / "services" / "Anyrouter.md"
            existing_path.parent.mkdir(parents=True)
            existing_path.write_text(
                "---\nid: resource:anyrouter\ntype: service\nstatus: watching\nevidence_status: community_evidence\n---\n\n"
                "# Anyrouter\n\n## 一句话判断\n\n旧模板页。\n\n## 我的反馈\n\n人工反馈要保留。\n",
                encoding="utf-8",
            )
            readings = {
                "readings": [
                    {
                        "topic_id": 323,
                        "title": "Anyrouter 复核",
                        "url": "https://linux.do/t/topic/323",
                        "summary": "复核 Anyrouter 风险。",
                        "resources": [
                            {
                                "id": "resource:anyrouter",
                                "name": "Anyrouter",
                                "status": "watching",
                                "evidence_status": "community_evidence",
                                "summary": "Anyrouter 仍需按版本复核。",
                                "risks": "SubAgent 和 Haiku 兼容性风险仍在。",
                            }
                        ],
                    }
                ]
            }

            ingest_session(config, task={"items": []}, readings=readings, batch_id="006", observed_at="2026-06-01T12:30:00+00:00")
            service_text = existing_path.read_text(encoding="utf-8")

        self.assertIn("## 稳定性", service_text)
        self.assertIn("## 隐私/安全风险", service_text)
        self.assertIn("## 价格/额度变化风险", service_text)
        self.assertIn("## 我的反馈\n\n人工反馈要保留。", service_text)

    def test_ingest_session_writes_collection_resource_with_collection_sections(self):
        from tools.linuxdo_knowledge.session import ingest_session

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            readings = {
                "readings": [
                    {
                        "topic_id": 324,
                        "title": "VS Code 插件线索",
                        "url": "https://linux.do/t/topic/324",
                        "summary": "讨论 VS Code BYOK 插件。",
                        "resources": [
                            {
                                "id": "resource:vscode-byok-ai-plugins",
                                "name": "VS Code BYOK AI 插件线索",
                                "category": "collection",
                                "status": "watching",
                                "evidence_status": "community_signal",
                                "summary": "收录 VS Code 中可配置自有 API 的 AI 插件线索。",
                                "risks": "插件权限、遥测和 API Key 存储需单独审查。",
                            }
                        ],
                    }
                ]
            }

            ingest_session(config, task={"items": []}, readings=readings, batch_id="008", observed_at="2026-06-01T12:30:00+00:00")
            collection_path = config.obsidian_vault_path / "10_Catalog" / "collections" / "VS-Code-BYOK-AI-插件线索.md"
            collection_exists = collection_path.exists()
            collection_text = collection_path.read_text(encoding="utf-8") if collection_exists else ""

        self.assertTrue(collection_exists)
        self.assertIn("type: collection", collection_text)
        for heading in (
            "## 一句话判断",
            "## 收录范围",
            "## 不收录什么",
            "## 阅读顺序",
            "## 代表页面",
            "## 风险",
            "## 来源",
        ):
            self.assertIn(heading, collection_text)

    def test_ingest_session_writes_concept_resource_with_concept_sections(self):
        from tools.linuxdo_knowledge.session import ingest_session

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            readings = {
                "readings": [
                    {
                        "topic_id": 325,
                        "title": "MCP 入门解释",
                        "url": "https://linux.do/t/topic/325",
                        "summary": "讨论 MCP 和 tool calling 的边界。",
                        "resources": [
                            {
                                "id": "resource:mcp-tool-calling-basics",
                                "name": "MCP 与 Tool Calling 入门解释",
                                "type": "concept",
                                "status": "watching",
                                "evidence_status": "community_evidence",
                                "summary": "解释模型工具调用、host 执行和上下文回灌。",
                                "limits": "个人解释不能替代官方规范。",
                            }
                        ],
                    }
                ]
            }

            ingest_session(config, task={"items": []}, readings=readings, batch_id="009", observed_at="2026-06-01T12:30:00+00:00")
            concept_path = config.obsidian_vault_path / "20_Knowledge" / "concepts" / "MCP-与-Tool-Calling-入门解释.md"
            concept_exists = concept_path.exists()
            concept_text = concept_path.read_text(encoding="utf-8") if concept_exists else ""

        self.assertTrue(concept_exists)
        self.assertIn("type: concept", concept_text)
        for heading in (
            "## 一句话判断",
            "## 概念边界",
            "## 常见误读",
            "## 适合沉淀什么",
            "## 不适合沉淀什么",
            "## 关键证据",
            "## 相关页面",
            "## 待验证",
            "## 来源",
        ):
            self.assertIn(heading, concept_text)
        self.assertNotIn("## 它是什么", concept_text)

    def test_ingest_session_writes_component_resource_with_component_sections(self):
        from tools.linuxdo_knowledge.session import ingest_session

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            readings = {
                "readings": [
                    {
                        "topic_id": 326,
                        "title": "Plan Mode 讨论",
                        "url": "https://linux.do/t/topic/326",
                        "summary": "讨论计划阶段如何作为工作流组件使用。",
                        "resources": [
                            {
                                "id": "resource:plan-mode",
                                "name": "Plan Mode",
                                "type": "component",
                                "status": "watching",
                                "evidence_status": "community_evidence",
                                "summary": "适合作为复杂任务开工前的澄清和拆解组件。",
                                "limits": "小改动不需要默认进入计划模式。",
                            }
                        ],
                    }
                ]
            }

            ingest_session(config, task={"items": []}, readings=readings, batch_id="010", observed_at="2026-06-01T12:30:00+00:00")
            component_path = config.obsidian_vault_path / "20_Knowledge" / "components" / "Plan-Mode.md"
            component_exists = component_path.exists()
            component_text = component_path.read_text(encoding="utf-8") if component_exists else ""

        self.assertTrue(component_exists)
        self.assertIn("type: component", component_text)
        for heading in (
            "## 一句话判断",
            "## 触发条件",
            "## 停止条件",
            "## 适合什么",
            "## 不适合什么",
            "## 关键证据",
            "## 相关对比",
            "## 待验证",
            "## 来源",
        ):
            self.assertIn(heading, component_text)
        self.assertNotIn("## 它是什么", component_text)

    def test_ingest_session_sparse_updates_preserve_hot_index_state(self):
        from tools.linuxdo_knowledge.session import ingest_session
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, load_hot_indexes, save_hot_index

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            ensure_knowledge_state(config)
            save_hot_index(
                config,
                "topic_index",
                {
                    "topics": {
                        "123": {
                            "topic_id": 123,
                            "title": "Codex workflow",
                            "url": "https://linux.do/t/topic/123",
                            "status": "active",
                            "watchlist": True,
                            "value_level": "high",
                            "resource_ids": ["candidate:codex-workflow"],
                            "claim_ids": ["claim:context-budget"],
                        }
                    }
                },
            )
            save_hot_index(
                config,
                "topic_update_state",
                {
                    "topics": {
                        "123": {
                            "topic_id": 123,
                            "highest_post_number": 18,
                            "highest_post_id": 98765,
                            "read_ranges": [{"from": 1, "to": 18}],
                            "content_fingerprint": "topic-fingerprint-1",
                        }
                    }
                },
            )
            save_hot_index(
                config,
                "resource_index",
                {
                    "resources": {
                        "candidate:codex-workflow": {
                            "id": "candidate:codex-workflow",
                            "name": "Codex Workflow",
                            "github_url": "https://github.com/example/workflow",
                            "category": "skill",
                            "evidence_status": "supporting",
                        }
                    }
                },
            )
            save_hot_index(
                config,
                "claim_index",
                {
                    "claims": {
                        "claim:context-budget": {
                            "id": "claim:context-budget",
                            "text": "长任务需要轻量索引",
                            "evidence_status": "supporting",
                        }
                    }
                },
            )

            ingest_session(
                config,
                task={"items": []},
                readings={
                    "readings": [
                        {
                            "topic_id": 123,
                            "title": "Codex workflow",
                            "reply_count": 19,
                            "resources": [{"id": "candidate:codex-workflow", "name": "Codex Workflow"}],
                            "claims": [{"id": "claim:context-budget", "text": "长任务需要轻量索引"}],
                        }
                    ]
                },
                batch_id="004",
                observed_at="2026-06-01T12:30:00+00:00",
            )
            indexes = load_hot_indexes(config)
            topic_index_state = indexes["topic_index"]["topics"]["123"]
            topic_state = indexes["topic_update_state"]["topics"]["123"]
            resource_state = indexes["resource_index"]["resources"]["candidate:codex-workflow"]
            claim_state = indexes["claim_index"]["claims"]["claim:context-budget"]

        self.assertTrue(topic_index_state["watchlist"])
        self.assertEqual(topic_index_state["status"], "active")
        self.assertEqual(topic_index_state["value_level"], "high")
        self.assertEqual(topic_index_state["url"], "https://linux.do/t/topic/123")
        self.assertEqual(topic_index_state["resource_ids"], ["candidate:codex-workflow"])
        self.assertEqual(topic_index_state["claim_ids"], ["claim:context-budget"])
        self.assertEqual(topic_state["read_reply_count"], 19)
        self.assertEqual(topic_state["highest_post_number"], 18)
        self.assertEqual(topic_state["highest_post_id"], 98765)
        self.assertEqual(topic_state["read_ranges"], [{"from": 1, "to": 18}])
        self.assertEqual(topic_state["content_fingerprint"], "topic-fingerprint-1")
        self.assertEqual(resource_state["github_url"], "https://github.com/example/workflow")
        self.assertEqual(resource_state["category"], "skill")
        self.assertEqual(resource_state["evidence_status"], "supporting")
        self.assertEqual(claim_state["evidence_status"], "supporting")

    def test_ingest_session_writes_evidence_edges_and_deduplicates_counter_queue(self):
        from tools.linuxdo_knowledge.session import ingest_session
        from tools.linuxdo_knowledge.state import load_hot_indexes

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            reading = {
                "topic_id": 901,
                "title": "Tool 失败反馈",
                "url": "https://linux.do/t/topic/901",
                "summary": "有人报告 Tool 在长任务里失败。",
                "resources": [{"id": "resource:tool", "name": "Tool"}],
                "claims": [{"id": "claim:tool-stable", "text": "Tool 在长任务中稳定"}],
                "evidence": [
                    {
                        "id": "evidence:linuxdo:901:failure",
                        "summary": "用户报告长任务中断。",
                        "stance": "reports_failure",
                        "confidence": "high",
                        "evidence_kind": "community_feedback",
                        "claim_refs": ["claim:tool-stable"],
                        "resource_refs": ["resource:tool"],
                        "minimal_context": "楼主复现两次。",
                        "risk": "稳定性风险",
                    }
                ],
            }

            ingest_session(
                config,
                task={"items": []},
                readings={"readings": [reading]},
                batch_id="edge-001",
                observed_at="2026-06-07T10:00:00+00:00",
            )
            ingest_session(
                config,
                task={"items": []},
                readings={"readings": [reading]},
                batch_id="edge-002",
                observed_at="2026-06-07T11:00:00+00:00",
            )
            indexes = load_hot_indexes(config)

        evidence = indexes["evidence_index"]["evidence"]["evidence:linuxdo:901:failure"]
        self.assertEqual(evidence["source_id"], "source:linuxdo:901")
        self.assertEqual(evidence["claim_ids"], ["claim:tool-stable"])
        self.assertEqual(evidence["resource_ids"], ["resource:tool"])
        self.assertEqual(evidence["stance"], "reports_failure")
        self.assertEqual(evidence["first_seen_at"], "2026-06-07T10:00:00+00:00")
        self.assertEqual(evidence["last_seen_at"], "2026-06-07T11:00:00+00:00")
        self.assertEqual(
            indexes["evidence_by_claim"]["claims"]["claim:tool-stable"]["counter_evidence_ids"],
            ["evidence:linuxdo:901:failure"],
        )
        self.assertEqual(
            indexes["evidence_by_resource"]["resources"]["resource:tool"]["counter_evidence_ids"],
            ["evidence:linuxdo:901:failure"],
        )
        queue = indexes["counter_evidence_queue"]["items"]
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["id"], "counter:claim:tool-stable:evidence:linuxdo:901:failure")
        self.assertEqual(queue[0]["status"], "open")
        self.assertEqual(queue[0]["last_seen_at"], "2026-06-07T11:00:00+00:00")

    def test_ingest_session_resolved_claim_preserves_existing_counter_evidence(self):
        from tools.linuxdo_knowledge.session import ingest_session
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, load_hot_indexes, save_hot_index

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            ensure_knowledge_state(config)
            save_hot_index(
                config,
                "claim_index",
                {
                    "claims": {
                        "claim:tool-risk": {
                            "id": "claim:tool-risk",
                            "text": "Tool 有稳定性风险",
                            "status": "disputed",
                            "opposes": ["旧反方：有人报告风险仍存在。"],
                        }
                    }
                },
            )

            ingest_session(
                config,
                task={"items": []},
                readings={
                    "readings": [
                        {
                            "topic_id": 123,
                            "title": "Tool 风险修复",
                            "url": "https://linux.do/t/topic/123",
                            "claims": [
                                {
                                    "id": "claim:tool-risk",
                                    "text": "Tool 有稳定性风险",
                                    "status": "resolved",
                                    "resolved_at": "2026-06-06T12:00:00+08:00",
                                    "fix_version": "v2.0",
                                    "verified_at": "2026-06-06T13:00:00+08:00",
                                }
                            ],
                        }
                    ]
                },
                batch_id="008",
                observed_at="2026-06-06T13:30:00+08:00",
            )
            indexes = load_hot_indexes(config)
            claim_state = indexes["claim_index"]["claims"]["claim:tool-risk"]
            claim_text = (
                config.obsidian_vault_path / "20_Knowledge" / "claims" / "claim-tool-risk.md"
            ).read_text(encoding="utf-8")

        self.assertEqual(claim_state["status"], "resolved")
        self.assertEqual(claim_state["resolved_at"], "2026-06-06T12:00:00+08:00")
        self.assertEqual(claim_state["fix_version"], "v2.0")
        self.assertEqual(claim_state["verified_at"], "2026-06-06T13:00:00+08:00")
        self.assertEqual(claim_state["opposes"], ["旧反方：有人报告风险仍存在。"])
        self.assertIn("旧反方：有人报告风险仍存在", claim_text)

    def test_ingest_session_records_claim_events_when_status_changes(self):
        from tools.linuxdo_knowledge.session import ingest_session
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, save_hot_index

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            ensure_knowledge_state(config)
            save_hot_index(
                config,
                "claim_index",
                {
                    "claims": {
                        "claim:tool-risk": {
                            "id": "claim:tool-risk",
                            "text": "Tool 有风险",
                            "status": "disputed",
                            "evidence_status": "open_question",
                        }
                    }
                },
            )

            ingest_session(
                config,
                task={"items": []},
                readings={
                    "readings": [
                        {
                            "topic_id": 902,
                            "title": "Tool 风险修复",
                            "url": "https://linux.do/t/topic/902",
                            "claims": [
                                {
                                    "id": "claim:tool-risk",
                                    "text": "Tool 有风险",
                                    "status": "resolved",
                                    "evidence_status": "supporting",
                                }
                            ],
                        }
                    ]
                },
                batch_id="event-001",
                observed_at="2026-06-07T12:00:00+00:00",
            )
            events = [
                json.loads(line)
                for line in (config.state_root / "claim_events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "claim_changed")
        self.assertEqual(events[0]["claim_id"], "claim:tool-risk")
        self.assertEqual(events[0]["changed_fields"], ["status", "evidence_status"])
        self.assertEqual(events[0]["before"]["status"], "disputed")
        self.assertEqual(events[0]["after"]["status"], "resolved")

    def test_ingest_session_ignores_corrupt_legacy_readings_all(self):
        from tools.linuxdo_knowledge.session import ingest_session

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            legacy_path = config.state_root / "readings_all.json"
            legacy_path.parent.mkdir(parents=True)
            legacy_path.write_text("{not valid json", encoding="utf-8")

            result = ingest_session(
                config,
                task={"items": []},
                readings={"readings": []},
                batch_id="004",
                observed_at="2026-06-01T12:30:00+00:00",
            )

        self.assertEqual(result, {"readings": 0})

    def test_ingest_session_counts_skipped_task_items_without_readings(self):
        from tools.linuxdo_knowledge.session import ingest_session
        from tools.linuxdo_knowledge.state import load_hot_indexes

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            result = ingest_session(
                config,
                task={
                    "items": [
                        {
                            "topic_id": 123,
                            "title": "重复帖",
                            "url": "https://linux.do/t/topic/123",
                            "action": "skip",
                            "skip_reason": "unchanged_read_topic",
                            "reply_count": 12,
                            "last_activity_at": "2026-06-01T11:00:00+00:00",
                        },
                        {
                            "topic_id": 124,
                            "title": "低价值帖",
                            "url": "https://linux.do/t/topic/124",
                            "action": "metadata_only",
                            "skip_reason": "low_value_topic",
                        },
                    ]
                },
                readings={"readings": []},
                batch_id="006",
                observed_at="2026-06-01T12:30:00+00:00",
            )
            indexes = load_hot_indexes(config)
            topic_index = indexes["topic_index"]["topics"]
            topic_update_state = indexes["topic_update_state"]["topics"]
            summary_exists = (config.state_root / "topic_summaries" / "123.json").exists()

        self.assertEqual(result, {"readings": 0})
        self.assertEqual(topic_index["123"]["skip_count"], 1)
        self.assertEqual(topic_index["123"]["skip_reason"], "unchanged_read_topic")
        self.assertEqual(topic_index["123"]["last_seen_at"], "2026-06-01T12:30:00+00:00")
        self.assertEqual(topic_index["124"]["skip_count"], 1)
        self.assertEqual(topic_index["124"]["skip_reason"], "low_value_topic")
        self.assertEqual(topic_update_state["123"]["reply_count"], 12)
        self.assertEqual(topic_update_state["123"]["last_activity_at"], "2026-06-01T11:00:00+00:00")
        self.assertFalse(summary_exists)

    def test_ingest_session_accepts_topics_readings_shape_and_corrupt_hot_indexes(self):
        from tools.linuxdo_knowledge.session import ingest_session

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            config.state_root.mkdir(parents=True)
            for name in ("topic_index", "topic_update_state", "resource_index", "claim_index"):
                (config.state_root / f"{name}.json").write_text("[]", encoding="utf-8")

            result = ingest_session(
                config,
                task=[],
                readings={
                    "topics": [
                        {
                            "topic_id": 123,
                            "title": "topics shape",
                            "url": "https://linux.do/t/topic/123",
                            "resources": [{"id": "candidate:tool", "name": "Tool"}],
                        }
                    ]
                },
                batch_id="005",
                observed_at="2026-06-01T12:30:00+00:00",
            )
            topic_index = json.loads((config.state_root / "topic_index.json").read_text(encoding="utf-8"))
            candidate_text = (
                config.obsidian_vault_path / "10_Catalog" / "candidates" / "Tool.md"
            ).read_text(encoding="utf-8")

        self.assertEqual(result, {"readings": 1})
        self.assertIn("123", topic_index["topics"])
        self.assertIn("status: candidate", candidate_text)


class FeedbackSyncTests(unittest.TestCase):
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

    def test_feedback_sync_reads_changed_pages_and_updates_indexes(self):
        from tools.linuxdo_knowledge.feedback import sync_feedback
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, load_hot_indexes

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            ensure_knowledge_state(config)
            page = config.obsidian_vault_path / "10_Catalog" / "resources" / "Tool.md"
            page.parent.mkdir(parents=True)
            page.write_text(
                "---\nid: resource:tool\ntype: resource\nstatus: deprioritized\nwatchlist: true\n---\n"
                "# Tool\n\n## Agent 摘要\n旧\n\n## 我的反馈\n不想继续看这个方向\n",
                encoding="utf-8",
            )
            claim_page = config.obsidian_vault_path / "20_Knowledge" / "claims" / "Claim.md"
            claim_page.parent.mkdir(parents=True)
            claim_page.write_text(
                "---\nid: \"claim:context-budget\"\ntype: claim\nstatus: disputed\n---\n"
                "# Claim\n\n## 我的反馈\n这个结论需要重新验证\n",
                encoding="utf-8",
            )

            result = sync_feedback(config, synced_at="2026-06-01T12:00:00+00:00")
            indexes = load_hot_indexes(config)

        self.assertEqual(result["changed_files"], 2)
        feedback_items = {item["id"]: item for item in indexes["user_feedback"]["items"]}
        self.assertEqual(feedback_items["resource:tool"]["feedback"], "不想继续看这个方向")
        self.assertEqual(feedback_items["claim:context-budget"]["feedback"], "这个结论需要重新验证")
        self.assertEqual(indexes["resource_index"]["resources"]["resource:tool"]["status"], "deprioritized")
        self.assertTrue(indexes["resource_index"]["resources"]["resource:tool"]["watchlist"])
        self.assertEqual(indexes["claim_index"]["claims"]["claim:context-budget"]["status"], "disputed")
        self.assertEqual(indexes["feedback_sync_state"]["last_sync_at"], "2026-06-01T12:00:00+00:00")

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

    def test_feedback_sync_skips_unchanged_files_and_updates_existing_feedback_item(self):
        from tools.linuxdo_knowledge.feedback import sync_feedback
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, load_hot_indexes

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            ensure_knowledge_state(config)
            page = config.obsidian_vault_path / "10_Catalog" / "resources" / "Tool.md"
            page.parent.mkdir(parents=True)
            page.write_text(
                "---\nid: resource:tool\ntype: resource\nstatus: active\n---\n"
                "# Tool\n\n## 我的反馈\n第一次反馈\n",
                encoding="utf-8",
            )

            first = sync_feedback(config, synced_at="2026-06-01T12:00:00+00:00")
            second = sync_feedback(config, synced_at="2026-06-01T13:00:00+00:00")
            page.write_text(
                "---\nid: resource:tool\ntype: resource\nstatus: deprioritized\n---\n"
                "# Tool\n\n## 我的反馈\n第二次反馈\n",
                encoding="utf-8",
            )
            third = sync_feedback(config, synced_at="2026-06-01T14:00:00+00:00")
            indexes = load_hot_indexes(config)

        self.assertEqual(first["changed_files"], 1)
        self.assertEqual(second["changed_files"], 0)
        self.assertEqual(third["changed_files"], 1)
        self.assertEqual(len(indexes["user_feedback"]["items"]), 1)
        self.assertEqual(indexes["user_feedback"]["items"][0]["feedback"], "第二次反馈")

    def test_feedback_sync_cli_writes_result_file(self):
        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            config_path = tmp_path / "config" / "knowledge_sources.json"
            config_path.parent.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "obsidian_vault_path": str(config.obsidian_vault_path),
                        "state_root": str(config.state_root),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            output_path = tmp_path / "feedback.json"

            exit_code = linuxdo_surf.main(
                [
                    "feedback-sync",
                    "--config",
                    str(config_path),
                    "--output",
                    str(output_path),
                ]
            )
            result = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(result, {"changed_files": 0})

    def test_feedback_sync_stops_feedback_at_next_same_level_heading(self):
        from tools.linuxdo_knowledge.feedback import sync_feedback
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, load_hot_indexes

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            ensure_knowledge_state(config)
            page = config.obsidian_vault_path / "10_Catalog" / "resources" / "Tool.md"
            page.parent.mkdir(parents=True)
            page.write_text(
                "---\nid: resource:tool\ntype: resource\nstatus: active\n---\n"
                "# Tool\n\n## 我的反馈\n只同步这一段\n\n## 后续计划\n这里不是反馈\n",
                encoding="utf-8",
            )

            sync_feedback(config, synced_at="2026-06-01T12:00:00+00:00")
            indexes = load_hot_indexes(config)

        self.assertEqual(indexes["user_feedback"]["items"][0]["feedback"], "只同步这一段")

    def test_feedback_sync_recovers_corrupt_feedback_hot_indexes(self):
        from tools.linuxdo_knowledge.feedback import sync_feedback
        from tools.linuxdo_knowledge.state import load_hot_indexes

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            config.state_root.mkdir(parents=True)
            for name in ("feedback_sync_state", "user_feedback", "resource_index", "claim_index"):
                (config.state_root / f"{name}.json").write_text("{not valid json", encoding="utf-8")
            page = config.obsidian_vault_path / "10_Catalog" / "resources" / "Tool.md"
            page.parent.mkdir(parents=True)
            page.write_text(
                "---\nid: resource:tool\ntype: resource\nstatus: active\n---\n# Tool\n\n## 我的反馈\n恢复同步\n",
                encoding="utf-8",
            )

            result = sync_feedback(config, synced_at="2026-06-01T12:00:00+00:00")
            indexes = load_hot_indexes(config)

        self.assertEqual(result, {"changed_files": 1})
        self.assertEqual(indexes["user_feedback"]["items"][0]["feedback"], "恢复同步")
        self.assertEqual(indexes["resource_index"]["resources"]["resource:tool"]["status"], "active")


class KnowledgeQualityRulesTests(unittest.TestCase):
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

    def test_quality_audit_flags_template_resource_and_source_evidence_heading(self):
        from tools.linuxdo_knowledge.quality_audit import audit_markdown_page

        text = """---
id: resource:demo
type: resource
status: watching
---

# Demo

## 一句话判断

Demo 是候选资源，当前记录显示它被多次提及；是否值得采用要看来源证据、维护状态和反方反馈。

## 来源证据

- 高相关：这是旧摘要...

## 我的反馈
"""
        issues = audit_markdown_page("10_Catalog/resources/Demo.md", text)
        codes = {issue["code"] for issue in issues}

        self.assertIn("template_residue", codes)
        self.assertIn("legacy_heading", codes)
        self.assertIn("banned_phrase", codes)
        self.assertIn("trailing_ellipsis", codes)

    def test_quality_audit_accepts_curated_resource_shape(self):
        from tools.linuxdo_knowledge.quality_audit import audit_markdown_page

        text = """---
id: resource:demo
type: resource
status: watching
watchlist: false
---

# Demo

## 一句话判断

Demo 是一个可继续观察的工具；当前只有少量社区体验，采用前需要确认维护状态。

## 它是什么

Demo 解决的是命令行内的任务编排，而不是模型路由或 API 中转。

## 适合什么

- 适合想把重复步骤写成显式流程的人。

## 不适合什么

- 不适合只想临时问答的人。

## 当前结论

先观察，不作为默认推荐。

## 关键证据

- [[linuxdo-topic-1]]：有用户描述了使用场景和限制。

## 反方与风险

- 维护状态需要复核。

## 相关竞品

- [[Other Demo]]

## 待验证

- 下次遇到 GitHub 链接时查 release 和 issue。

## 来源

- [[linuxdo-topic-1]]

## 我的反馈
"""
        self.assertEqual(audit_markdown_page("10_Catalog/resources/Demo.md", text), [])

    def test_cli_knowledge_audit_writes_report(self):
        with TemporaryDirectoryPath() as tmp_path:
            vault_path = tmp_path / "vault"
            page_path = vault_path / "10_Catalog" / "resources" / "Demo.md"
            page_path.parent.mkdir(parents=True)
            page_path.write_text(
                "---\nid: resource:demo\ntype: resource\nstatus: watching\n---\n"
                "# Demo\n\n## 一句话判断\n\n高相关：旧摘要...\n\n## 我的反馈\n",
                encoding="utf-8",
            )
            config_path = tmp_path / "config" / "knowledge_sources.json"
            config_path.parent.mkdir()
            config_path.write_text(
                json.dumps({"obsidian_vault_path": str(vault_path)}, ensure_ascii=False),
                encoding="utf-8",
            )
            output_path = tmp_path / "quality_audit.json"

            exit_code = linuxdo_surf.main(
                ["knowledge-audit", "--config", str(config_path), "--output", str(output_path)]
            )
            report = json.loads(output_path.read_text(encoding="utf-8"))
            codes = {issue["code"] for issue in report["issues"]}

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["pages_scanned"], 1)
        self.assertIn("banned_phrase", codes)
        self.assertIn("missing_section", codes)

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
        self.assertEqual(report["pages_scanned"], 1)

    def test_quality_audit_ledger_layer_uses_ledger_rules_not_human_lint(self):
        from tools.linuxdo_knowledge.quality_audit import audit_vault

        with TemporaryDirectoryPath() as tmp_path:
            vault = tmp_path / "vault"
            evidence = vault / "_system" / "evidence" / "linuxdo" / "topic-1.md"
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text("# Machine Evidence\n\n## 来源证据\n\nsource: linuxdo\ntopic_id: 1\n", encoding="utf-8")

            report = audit_vault(vault, layer="ledger")

        self.assertEqual(report["layer"], "ledger")
        self.assertEqual(report["pages_scanned"], 1)
        self.assertEqual(report["issues"], [])

    def test_cli_knowledge_audit_paths_file_scans_batch_paths_only(self):
        with TemporaryDirectoryPath() as tmp_path:
            vault_path = tmp_path / "vault"
            target = vault_path / "10_Catalog" / "resources" / "Target.md"
            other = vault_path / "10_Catalog" / "resources" / "Other.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("---\nid: resource:target\ntype: resource\n---\n# Target\n", encoding="utf-8")
            other.write_text("---\nid: resource:other\ntype: resource\n---\n# Other\n", encoding="utf-8")
            config_path = tmp_path / "config" / "knowledge_sources.json"
            config_path.parent.mkdir()
            config_path.write_text(json.dumps({"obsidian_vault_path": str(vault_path)}, ensure_ascii=False), encoding="utf-8")
            paths_file = tmp_path / "paths.txt"
            paths_file.write_text("10_Catalog/resources/Target.md\n", encoding="utf-8")
            output_path = tmp_path / "quality_audit.json"

            exit_code = linuxdo_surf.main(
                [
                    "knowledge-audit",
                    "--config",
                    str(config_path),
                    "--paths-file",
                    str(paths_file),
                    "--output",
                    str(output_path),
                ]
            )
            report = json.loads(output_path.read_text(encoding="utf-8"))

        issue_paths = {issue["path"] for issue in report["issues"]}
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["layer"], "batch")
        self.assertEqual(report["pages_scanned"], 1)
        self.assertIn("10_Catalog/resources/Target.md", issue_paths)
        self.assertNotIn("10_Catalog/resources/Other.md", issue_paths)

    def test_quality_required_sections_by_page_type_are_distinct(self):
        from tools.linuxdo_knowledge.quality import required_sections_for_page_type

        self.assertIn("隐私/安全风险", required_sections_for_page_type("service"))
        self.assertIn("核心步骤", required_sections_for_page_type("workflow"))
        self.assertIn("概念边界", required_sections_for_page_type("concept"))
        self.assertIn("触发条件", required_sections_for_page_type("component"))
        self.assertIn("比较范围", required_sections_for_page_type("comparison"))
        self.assertNotIn("隐私/安全风险", required_sections_for_page_type("resource"))

    def test_quality_lint_flags_generic_template_sentences(self):
        from tools.linuxdo_knowledge.quality import lint_human_markdown

        issues = lint_human_markdown("Demo 是候选资源，当前记录显示它被多次提及。", page_name="Demo")

        self.assertIn("template_residue", {issue.code for issue in issues})

    def test_quality_audit_uses_shared_required_sections(self):
        from tools.linuxdo_knowledge.quality_audit import audit_markdown_page

        text = """---
id: service:demo
type: service
status: watching
---

# Demo

## 一句话判断

Demo 是一个待观察服务。

## 它是什么

Demo 提供 API 中转能力。

## 适合什么

- 适合低风险试用。

## 不适合什么

- 不适合承载敏感数据。

## 当前结论

先观察。

## 关键证据

- [[linuxdo-topic-1]]

## 反方与风险

- 稳定性需要复核。

## 相关竞品

- [[Other Demo]]

## 待验证

- 需要核对价格。

## 来源

- [[linuxdo-topic-1]]
"""
        issues = audit_markdown_page("10_Catalog/services/Demo.md", text)

        self.assertIn(
            {"path": "10_Catalog/services/Demo.md", "code": "missing_section", "message": "缺少章节：隐私/安全风险"},
            issues,
        )

    def test_context_pack_uses_hot_indexes_and_changed_feedback_only(self):
        from tools.linuxdo_knowledge.context_pack import build_context_pack
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, save_hot_index

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            ensure_knowledge_state(config)
            (config.state_root / "readings_all.json").write_text("{not valid json", encoding="utf-8")
            save_hot_index(
                config,
                "resource_index",
                {"resources": {"superpowers": {"title": "Superpowers", "status": "watching", "watchlist": True}}},
            )
            save_hot_index(
                config,
                "topic_update_state",
                {"topics": {"2151853": {"title": "Superpowers 讨论", "reply_count": 32, "read_reply_count": 17}}},
            )
            save_hot_index(
                config,
                "user_feedback",
                {"items": [{"id": "resource:superpowers", "feedback": "偏好轻量，不默认重流程。"}]},
            )

            pack = build_context_pack(config, focus="superpowers", limit=20)

        self.assertEqual(pack["focus"], "superpowers")
        self.assertEqual(pack["watchlist"][0]["title"], "Superpowers")
        self.assertEqual(pack["topic_updates"][0]["unread_replies"], 15)
        self.assertIn("偏好轻量", pack["feedback"][0]["feedback_preview"])
        self.assertNotIn("readings_all", json.dumps(pack, ensure_ascii=False))

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
                        "resource:watch": {
                            "id": "resource:watch",
                            "title": "Watch",
                            "status": "candidate",
                            "watchlist": True,
                        },
                        "resource:observe": {
                            "id": "resource:observe",
                            "title": "Observe",
                            "status": "watching",
                            "watchlist": False,
                        },
                    }
                },
            )

            pack = build_context_pack(config, limit=20)

        self.assertEqual([item["id"] for item in pack["watchlist"]], ["resource:watch"])

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

    def test_metadata_refresh_clears_pending_flag_after_complete_live_metadata(self):
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
                            "metadata_refresh_needed": True,
                            "metadata_refresh_reason": "missing_reply_count_or_last_activity_at",
                            "metadata_refresh_marked_at": "2026-06-06T09:00:00+08:00",
                        }
                    }
                },
            )

            result = apply_topic_metadata_refresh(
                config,
                [
                    {
                        "topic_id": 123,
                        "reply_count": 14,
                        "last_activity_at": "2026-06-06T10:00:00+08:00",
                    }
                ],
                refreshed_at="2026-06-06T10:01:00+08:00",
            )
            indexes = load_hot_indexes(config)
            topic = indexes["topic_update_state"]["topics"]["123"]

        self.assertEqual(result["updated"], 1)
        self.assertNotIn("metadata_refresh_needed", topic)
        self.assertNotIn("metadata_refresh_reason", topic)
        self.assertNotIn("metadata_refresh_marked_at", topic)

    def test_metadata_refresh_blocked_parks_pending_topic(self):
        from tools.linuxdo_knowledge.index_audit import audit_knowledge_indexes
        from tools.linuxdo_knowledge.metadata_refresh import park_topic_metadata_refresh_blocked
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, load_hot_indexes, save_hot_index

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            ensure_knowledge_state(config)
            save_hot_index(
                config,
                "topic_index",
                {"topics": {"123": {"topic_id": 123, "title": "待补帖", "url": "https://linux.do/t/topic/123"}}},
            )
            save_hot_index(
                config,
                "topic_update_state",
                {
                    "topics": {
                        "123": {
                            "topic_id": 123,
                            "metadata_refresh_needed": True,
                            "metadata_refresh_reason": "missing_reply_count_or_last_activity_at",
                            "metadata_refresh_marked_at": "2026-06-06T09:00:00+08:00",
                        }
                    }
                },
            )

            result = park_topic_metadata_refresh_blocked(
                config,
                [
                    {
                        "topic_id": 123,
                        "title": "找不到页面 - LINUX DO",
                        "url": "https://linux.do/t/topic/123?page=0",
                        "fetch_status": "blocked_or_not_found",
                        "error": "blocked_or_not_found_or_permission",
                        "source": "chrome_topic_page_fallback_dom",
                        "needed_human_action": "manual_topic_check",
                    }
                ],
                parked_at="2026-06-06T10:01:00+08:00",
            )
            indexes = load_hot_indexes(config)
            topic = indexes["topic_update_state"]["topics"]["123"]
            audit = audit_knowledge_indexes(config)

        self.assertEqual(result["parked"], 1)
        self.assertNotIn("metadata_refresh_needed", topic)
        self.assertEqual(topic["title"], "待补帖")
        self.assertEqual(topic["url"], "https://linux.do/t/topic/123")
        self.assertEqual(topic["metadata_refresh_blocked"], True)
        self.assertEqual(topic["metadata_refresh_blocked_page_title"], "找不到页面 - LINUX DO")
        self.assertEqual(topic["metadata_refresh_blocked_page_url"], "https://linux.do/t/topic/123?page=0")
        self.assertEqual(topic["metadata_refresh_blocked_reason"], "blocked_or_not_found_or_permission")
        self.assertEqual(audit["issue_counts"]["metadata_refresh_pending"], 0)
        self.assertEqual(audit["issue_counts"]["metadata_refresh_blocked"], 1)
        self.assertEqual(audit["issue_counts"]["topic_update_missing"], 0)

    def test_cli_metadata_refresh_writes_result_file(self):
        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            config_path = tmp_path / "config" / "knowledge_sources.json"
            config_path.parent.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "obsidian_vault_path": str(config.obsidian_vault_path),
                        "state_root": str(config.state_root),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            input_path = tmp_path / "metadata.json"
            input_path.write_text(
                json.dumps({"items": [{"topic_id": 456, "reply_count": 3}]}, ensure_ascii=False),
                encoding="utf-8",
            )
            output_path = tmp_path / "metadata_result.json"

            exit_code = linuxdo_surf.main(
                [
                    "metadata-refresh",
                    "--config",
                    str(config_path),
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                ]
            )
            result = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(result["updated"], 1)

    def test_cli_metadata_refresh_blocked_writes_result_file(self):
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, save_hot_index

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            ensure_knowledge_state(config)
            save_hot_index(
                config,
                "topic_update_state",
                {"topics": {"456": {"topic_id": 456, "metadata_refresh_needed": True}}},
            )
            config_path = tmp_path / "config" / "knowledge_sources.json"
            config_path.parent.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "obsidian_vault_path": str(config.obsidian_vault_path),
                        "state_root": str(config.state_root),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            input_path = tmp_path / "blocked.json"
            input_path.write_text(
                json.dumps({"items": [{"topic_id": 456, "fetch_status": "challenge_or_loading"}]}, ensure_ascii=False),
                encoding="utf-8",
            )
            output_path = tmp_path / "blocked_result.json"

            exit_code = linuxdo_surf.main(
                [
                    "metadata-refresh-blocked",
                    "--config",
                    str(config_path),
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                ]
            )
            result = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(result["parked"], 1)

    def test_knowledge_prepare_runs_daily_startup_pipeline(self):
        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            config_path = tmp_path / "config" / "knowledge_sources.json"
            config_path.parent.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "obsidian_vault_path": str(config.obsidian_vault_path),
                        "state_root": str(config.state_root),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            output_dir = tmp_path / "output"

            exit_code = linuxdo_surf.main(
                [
                    "knowledge-prepare",
                    "--config",
                    str(config_path),
                    "--batch-size",
                    "3",
                    "--focus",
                    "superpowers",
                    "--output-dir",
                    str(output_dir),
                ]
            )
            manifest_path = output_dir / "knowledge_prepare_latest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest_exists = manifest_path.exists()
            artifact_exists = {
                key: (tmp_path / manifest[key]).exists()
                for key in ("feedback_sync", "bookmark_sync", "context_pack", "knowledge_task")
            }

        self.assertEqual(exit_code, 0)
        self.assertTrue(manifest_exists)
        self.assertEqual(manifest["history_policy"], "load_hot_indexes_only")
        self.assertTrue(all(artifact_exists.values()), artifact_exists)

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

    def test_knowledge_consume_frontier_removes_read_topics_and_writes_payload(self):
        from tools.linuxdo_knowledge.state import load_hot_indexes, save_hot_index

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            config_path = tmp_path / "config" / "knowledge_sources.json"
            config_path.parent.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "state_root": str(config.state_root),
                        "obsidian_vault_path": str(config.obsidian_vault_path),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            save_hot_index(
                config,
                "frontier_queue",
                {
                    "items": [
                        {"topic_id": 101, "title": "已读 items"},
                        {"topic_id": 202, "title": "保留 items"},
                    ],
                    "queue": [
                        {"topic_id": "101", "title": "已读 queue"},
                        {"topic_id": 303, "title": "保留 queue"},
                    ],
                },
            )
            readings_path = tmp_path / "readings.json"
            readings_path.write_text(
                json.dumps(
                    {
                        "browser_summary": "读完 101",
                        "readings": [{"topic_id": 101, "summary": "值得收录"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            exit_code = linuxdo_surf.main(
                [
                    "knowledge-consume-frontier",
                    "--config",
                    str(config_path),
                    "--readings",
                    str(readings_path),
                    "--batch-id",
                    "frontier-001",
                ]
            )
            indexes = load_hot_indexes(config)
            frontier = indexes["frontier_queue"]
            output_path = tmp_path / "output" / "linuxdo_surf" / "frontier-001_frontier_consumed.json"
            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual([item["topic_id"] for item in frontier["items"]], [202])
        self.assertEqual([item["topic_id"] for item in frontier["queue"]], [303])
        self.assertEqual(frontier["last_consumed_batch"], "frontier-001")
        self.assertEqual(frontier["last_consumed_topic_ids"], [101])
        self.assertIn("last_consumed_at", frontier)
        self.assertIn("updated_at", frontier)
        self.assertEqual(payload["batch_id"], "frontier-001")
        self.assertEqual(payload["topic_ids"], [101])
        self.assertEqual([item["title"] for item in payload["items"]], ["已读 items"])
        self.assertEqual(payload["browser_summary"], "读完 101")

    def test_home_uses_three_entry_reading_paths(self):
        from tools.linuxdo_knowledge.second_pass import _write_home_index

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            _write_home_index(config, "2026-06-06T12:00:00+08:00")
            text = (config.obsidian_vault_path / "00_Home" / "index.md").read_text(encoding="utf-8")

        self.assertIn("按主题读", text)
        self.assertIn("按选择读", text)
        self.assertIn("采用前复核", text)
        self.assertLessEqual(text.count("[[怎么读这个知识库|怎么读这个知识库]]"), 1)

    def test_review_queue_groups_resolved_items_out_of_active_section(self):
        from tools.linuxdo_knowledge.second_pass import CATEGORY_DEFS, _write_review_queue

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            classified = {category["key"]: [] for category in CATEGORY_DEFS}
            classified["api_relay"] = [
                {"id": 1, "title": "Open item", "url": "https://linux.do/t/topic/1", "status": "open"},
                {"id": 2, "title": "Deferred item", "url": "https://linux.do/t/topic/2", "status": "deferred"},
                {"id": 3, "title": "Resolved item", "url": "https://linux.do/t/topic/3", "status": "resolved"},
            ]

            _write_review_queue(config, classified, "2026-06-06T12:00:00+08:00")
            text = (
                config.obsidian_vault_path / "90_Inbox" / "review-queue" / "需要回原文复核.md"
            ).read_text(encoding="utf-8")

        active_section = text.split("## 需要处理", 1)[1].split("## 暂时延后", 1)[0]
        self.assertIn("Open item", active_section)
        self.assertNotIn("Deferred item", active_section)
        self.assertNotIn("Resolved item", active_section)
        self.assertIn("Deferred item", text.split("## 暂时延后", 1)[1].split("## 已处理", 1)[0])
        self.assertIn("Resolved item", text.split("## 已处理", 1)[1])

    def test_review_queue_resolved_item_status_is_parsed(self):
        from tools.linuxdo_knowledge.feedback import parse_markdown_page

        with TemporaryDirectoryPath() as tmp_path:
            path = tmp_path / "review.md"
            path.write_text(
                "---\nid: review:item-1\ntype: review\nstatus: resolved\n---\n"
                "# Item\n\n## 我的反馈\n\n已处理。\n",
                encoding="utf-8",
            )

            parsed = parse_markdown_page(path)

        self.assertEqual(parsed["status"], "resolved")

    def test_alias_registry_maps_name_to_canonical_id(self):
        from tools.linuxdo_knowledge.aliases import canonicalize_name

        self.assertEqual(canonicalize_name("Vibe-Coding"), "Vibecoding")
        self.assertEqual(canonicalize_name("cli proxy api"), "CPA")
        self.assertEqual(canonicalize_name("opencode"), "OpenCode")


class LegacyMigrationTests(unittest.TestCase):
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

    def test_quality_lint_flags_old_summary_noise(self):
        from tools.linuxdo_knowledge.quality import lint_human_markdown

        issues = lint_human_markdown(
            "## 关键证据\n\n- 高相关：风佬巨作 v5.0，zcf...\n",
            page_name="Demo",
        )

        issue_codes = {issue.code for issue in issues}
        self.assertIn("banned_phrase", issue_codes)
        self.assertIn("trailing_ellipsis", issue_codes)
        self.assertIn("opaque_term", issue_codes)

    def test_quality_lint_allows_page_own_short_name(self):
        from tools.linuxdo_knowledge.quality import lint_human_markdown

        own_page_issues = lint_human_markdown(
            "---\nid: resource:zcf\n---\n# ZCF\n\n## 一句话判断\n\nZCF 是配置工具线索。\n",
            page_name="10_Catalog/resources/ZCF.md",
        )
        other_page_issues = lint_human_markdown(
            "## 关键证据\n\n- 这里直接写 zcf，没有解释它是什么。\n",
            page_name="10_Catalog/resources/Demo.md",
        )

        self.assertNotIn("opaque_term", {issue.code for issue in own_page_issues})
        self.assertIn("opaque_term", {issue.code for issue in other_page_issues})

    def test_quality_lint_ignores_frontmatter_machine_ids(self):
        from tools.linuxdo_knowledge.quality import lint_human_markdown

        issues = lint_human_markdown(
            "---\nid: workflow:zcf-claude-codex-config\n---\n"
            "# Zero-Config Code Flow Claude Code/Codex 初始化流\n\n"
            "## 一句话判断\n\n"
            "Zero-Config Code Flow 是一键配置工具线索。\n",
            page_name="10_Catalog/workflows/ZCF-Claude-Code-Codex-初始化流.md",
        )

        self.assertNotIn("opaque_term", {issue.code for issue in issues})

    def test_quality_normalizes_aliases_and_detects_broad_objects(self):
        from tools.linuxdo_knowledge.quality import classify_knowledge_object, normalize_resource_name

        self.assertEqual(normalize_resource_name("Vibe-Coding"), ("vibecoding", "Vibecoding"))
        self.assertEqual(normalize_resource_name("ccswitch"), ("cc-switch", "CC-Switch"))
        self.assertEqual(classify_knowledge_object("公益站"), "collection")
        self.assertEqual(classify_knowledge_object("New API"), "service")
        self.assertEqual(classify_knowledge_object("Superpowers"), "workflow")

    def test_quality_classifier_routes_known_confusing_objects(self):
        from tools.linuxdo_knowledge.quality import classify_knowledge_object, normalize_resource_name

        cases = {
            "公益站": "collection",
            "API 中转": "collection",
            "third-party API": "collection",
            "CPA": "service",
            "CLIProxyAPI": "service",
            "OpenRouter": "service",
            "Superpowers": "workflow",
            "Trellis": "workflow",
            "grill-me": "component",
            "Context Engineering": "concept",
            "Vibe-Coding": "concept",
            "Codex CLI": "resource",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(classify_knowledge_object(name), expected)

        self.assertEqual(normalize_resource_name("Vibe-Coding"), ("vibecoding", "Vibecoding"))
        self.assertEqual(normalize_resource_name("CLIProxyAPI"), ("cpa", "CPA"))

    def test_knowledge_migrate_legacy_writes_new_vault_structure_without_old_dirs(self):
        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            config_path = tmp_path / "config" / "knowledge_sources.json"
            config_path.parent.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "obsidian_vault_path": str(config.obsidian_vault_path),
                        "state_root": str(config.state_root),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            legacy_path = tmp_path / "readings_all.json"
            legacy_path.write_text(
                json.dumps(
                    {
                        "readings": [
                            {
                                "id": 10,
                                "title": "Superpowers 讨论",
                                "url": "https://linux.do/t/topic/10",
                                "summary": "讨论 Superpowers 的 token 成本和替代方案。",
                                "value_tag": "马上试",
                                "tools": ["Superpowers", "AI"],
                                "github_repos": ["owner/repo"],
                                "positive_feedback": ["有完整工程纪律。"],
                                "negative_feedback": ["小任务偏重。"],
                                "high_value_replies": [
                                    {"post_number": 2, "author": "alice", "text": "建议按任务重量路由。"}
                                ],
                                "visible_post_count": 3,
                            },
                            {
                                "id": 11,
                                "title": "低价值水贴",
                                "url": "https://linux.do/t/topic/11",
                                "summary": "只有 mark。",
                                "value_tag": "暂时跳过",
                                "tools": ["Claude"],
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            output_path = tmp_path / "migrate.json"

            exit_code = linuxdo_surf.main(
                [
                    "knowledge-migrate-legacy",
                    "--config",
                    str(config_path),
                    "--input",
                    str(legacy_path),
                    "--batch-size",
                    "1",
                    "--resource-limit",
                    "5",
                    "--output",
                    str(output_path),
                ]
            )
            result = json.loads(output_path.read_text(encoding="utf-8"))
            topic_index = json.loads((config.state_root / "topic_index.json").read_text(encoding="utf-8"))
            source_exists = (
                config.obsidian_vault_path / "_system" / "sources" / "linuxdo" / "linuxdo-topic-10.md"
            ).exists()
            evidence_exists = (
                config.obsidian_vault_path / "_system" / "evidence" / "linuxdo" / "linuxdo-10-source-note.md"
            ).exists()
            workflow_path = config.obsidian_vault_path / "10_Catalog" / "workflows" / "Superpowers.md"
            workflow_exists = workflow_path.exists()
            workflow_text = workflow_path.read_text(encoding="utf-8") if workflow_exists else ""
            session_texts = [
                path.read_text(encoding="utf-8")
                for path in (config.obsidian_vault_path / "90_Inbox" / "sessions").glob("*.md")
            ]
            review_path = config.obsidian_vault_path / "90_Inbox" / "review-queue" / "资料整理复核.md"
            review_exists = review_path.exists()
            review_text = review_path.read_text(encoding="utf-8") if review_exists else ""
            old_catalog_exists = (config.obsidian_vault_path / "catalog").exists()

        self.assertEqual(exit_code, 0)
        self.assertEqual(result, {"readings": 2, "legacy_batches": 2, "resource_candidates": 2})
        self.assertTrue(source_exists)
        self.assertTrue(evidence_exists)
        self.assertTrue(workflow_exists)
        self.assertIn("type: workflow", workflow_text)
        self.assertIn("status: needs_rewrite", workflow_text)
        self.assertNotIn("evidence_status: legacy_summary", workflow_text)
        self.assertIn("讨论信号", workflow_text)
        self.assertNotIn("证据权重", workflow_text)
        assert_no_generator_residue(self, workflow_text, page_name="Superpowers.md")
        for index, session_text in enumerate(session_texts):
            assert_no_generator_residue(self, session_text, page_name=f"session-{index}")
        self.assertTrue(review_exists)
        self.assertIn("knowledge/linuxdo", review_text)
        self.assertNotIn("review/source-triage", review_text)
        assert_no_generator_residue(self, review_text, page_name="资料整理复核.md")
        self.assertEqual(topic_index["topics"]["10"]["status"], "active")
        self.assertEqual(topic_index["topics"]["11"]["status"], "deprioritized")
        self.assertFalse(old_catalog_exists)

    def test_knowledge_migrate_legacy_does_not_promote_broad_collection_to_resource_card(self):
        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            config_path = tmp_path / "config" / "knowledge_sources.json"
            config_path.parent.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "obsidian_vault_path": str(config.obsidian_vault_path),
                        "state_root": str(config.state_root),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            legacy_path = tmp_path / "readings_all.json"
            legacy_path.write_text(
                json.dumps(
                    {
                        "readings": [
                            {
                                "id": 12,
                                "title": "公益站和 Superpowers",
                                "url": "https://linux.do/t/topic/12",
                                "summary": "讨论公益站收集和 Superpowers。",
                                "value_tag": "high",
                                "tools": ["公益站", "Superpowers"],
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            output_path = tmp_path / "migrate.json"

            exit_code = linuxdo_surf.main(
                [
                    "knowledge-migrate-legacy",
                    "--config",
                    str(config_path),
                    "--input",
                    str(legacy_path),
                    "--resource-limit",
                    "5",
                    "--output",
                    str(output_path),
                ]
            )
            result = json.loads(output_path.read_text(encoding="utf-8"))
            broad_card_exists = (config.obsidian_vault_path / "10_Catalog" / "candidates" / "公益站.md").exists()
            superpowers_card_exists = (config.obsidian_vault_path / "10_Catalog" / "workflows" / "Superpowers.md").exists()

        self.assertEqual(exit_code, 0)
        self.assertEqual(result["resource_candidates"], 1)
        self.assertFalse(broad_card_exists)
        self.assertTrue(superpowers_card_exists)

    def test_knowledge_migrate_legacy_sanitizes_existing_broad_and_alias_candidate_pages(self):
        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            config_path = tmp_path / "config" / "knowledge_sources.json"
            config_path.parent.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "obsidian_vault_path": str(config.obsidian_vault_path),
                        "state_root": str(config.state_root),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            candidate_dir = config.obsidian_vault_path / "10_Catalog" / "candidates"
            candidate_dir.mkdir(parents=True)
            (candidate_dir / "API-中转.md").write_text(
                "---\nid: resource:api-中转\ntype: candidate\nstatus: candidate\n---\n"
                "# API 中转\n\n## 来源证据摘要\n\n累计证据中多次出现，证据权重 9。\n\n## 我的反馈\n\n保留这句\n",
                encoding="utf-8",
            )
            (candidate_dir / "公益站.md").write_text(
                "---\nid: resource:公益站\ntype: candidate\nstatus: candidate\n---\n"
                "# 公益站\n\n## 初步判断\n\n高相关。旧摘要。\n\n## 我的反馈\n",
                encoding="utf-8",
            )
            (candidate_dir / "ccswitch.md").write_text(
                "---\nid: resource:ccswitch\ntype: candidate\nstatus: candidate\n---\n"
                "# ccswitch\n\n## 初步判断\n\n高相关。\n\n## 我的反馈\n\n我还在看这个\n",
                encoding="utf-8",
            )
            (candidate_dir / "cc-switch.md").write_text(
                "---\nid: resource:cc-switch\ntype: candidate\nstatus: needs_rewrite\n---\n# CC Switch\n\n",
                encoding="utf-8",
            )
            legacy_path = tmp_path / "readings_all.json"
            legacy_path.write_text(
                json.dumps(
                    {
                        "readings": [
                            {
                                "id": 13,
                                "title": "CC-Switch 讨论（风佬巨作）……",
                                "url": "https://linux.do/t/topic/13",
                                "summary": "讨论 CC-Switch。",
                                "value_tag": "high",
                                "tools": ["ccswitch", "Superpowers"],
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            output_path = tmp_path / "migrate.json"

            exit_code = linuxdo_surf.main(
                [
                    "knowledge-migrate-legacy",
                    "--config",
                    str(config_path),
                    "--input",
                    str(legacy_path),
                    "--resource-limit",
                    "5",
                    "--output",
                    str(output_path),
                ]
            )
            api_text = (candidate_dir / "API-中转.md").read_text(encoding="utf-8")
            public_text = (candidate_dir / "公益站.md").read_text(encoding="utf-8")
            alias_text = (candidate_dir / "ccswitch.md").read_text(encoding="utf-8")
            canonical_text = (candidate_dir / "CC-Switch.md").read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertIn("status: needs_rewrite", api_text)
        self.assertIn("保留这句", api_text)
        self.assertIn("集合入口", public_text)
        self.assertIn("status: duplicate", alias_text)
        self.assertIn("[[cc-switch|CC-Switch]]", alias_text)
        self.assertIn("我还在看这个", alias_text)
        for text in (api_text, public_text, alias_text, canonical_text):
            self.assertNotIn("高相关", text)
            self.assertNotIn("证据权重", text)
            self.assertNotIn("风佬巨作", text)
            self.assertNotRegex(text, r"\.\.\.|…")

    def test_knowledge_migrate_legacy_does_not_overwrite_curated_candidate_page(self):
        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            config_path = tmp_path / "config" / "knowledge_sources.json"
            config_path.parent.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "obsidian_vault_path": str(config.obsidian_vault_path),
                        "state_root": str(config.state_root),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            candidate_dir = config.obsidian_vault_path / "10_Catalog" / "candidates"
            candidate_dir.mkdir(parents=True)
            curated_page = candidate_dir / "Superpowers.md"
            curated_page.write_text(
                "---\nid: resource:superpowers\ntype: candidate\nstatus: watching\nevidence_status: community_evidence\n---\n"
                "# Superpowers\n\n## 一句话判断\n\n人工整理后的结论\n\n## 我的反馈\n\n人写反馈\n",
                encoding="utf-8",
            )
            legacy_path = tmp_path / "readings_all.json"
            legacy_path.write_text(
                json.dumps(
                    {
                        "readings": [
                            {
                                "id": 14,
                                "title": "Superpowers",
                                "url": "https://linux.do/t/topic/14",
                                "summary": "旧摘要不应覆盖。",
                                "value_tag": "high",
                                "tools": ["Superpowers"],
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            output_path = tmp_path / "migrate.json"

            exit_code = linuxdo_surf.main(
                [
                    "knowledge-migrate-legacy",
                    "--config",
                    str(config_path),
                    "--input",
                    str(legacy_path),
                    "--resource-limit",
                    "5",
                    "--output",
                    str(output_path),
                ]
            )
            text = curated_page.read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertIn("人工整理后的结论", text)
        self.assertIn("人写反馈", text)
        self.assertNotIn("旧摘要不应覆盖", text)
        self.assertIn("status: watching", text)

    def test_knowledge_organize_existing_writes_guides_comparisons_and_review_queue(self):
        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            config_path = tmp_path / "config" / "knowledge_sources.json"
            config_path.parent.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "obsidian_vault_path": str(config.obsidian_vault_path),
                        "state_root": str(config.state_root),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            readings_path = tmp_path / "readings_all.json"
            readings_path.write_text(
                json.dumps(
                    {
                        "readings": [
                            {
                                "id": 20,
                                "title": "Superpowers 和轻量 skill 怎么选",
                                "url": "https://linux.do/t/topic/20",
                                "summary": "Batch 旧帖：本批讨论 Superpowers、Trellis 和轻量 spec skill 的取舍。",
                                "value_tag": "high",
                                "tools": ["Superpowers", "Trellis"],
                                "positive_feedback": ["Superpowers 有完整工程纪律。"],
                                "negative_feedback": ["小任务偏重。"],
                                "comparison_notes": ["和轻量提问式 skill 相比，Superpowers 更适合复杂任务。"],
                                "risk_notes": ["默认全开会增加 token 成本。"],
                                "visible_post_count": 80,
                            },
                            {
                                "id": 21,
                                "title": "公益 API 中转稳定性反馈",
                                "url": "https://linux.do/t/topic/21",
                                "summary": "讨论中转站、OpenRouter、New API 的稳定性和模型缩水风险。",
                                "value_tag": "medium",
                                "tools": ["OpenRouter", "New API"],
                                "comparison_notes": ["中转和官方渠道在上下文与稳定性上差异明显。"],
                                "risk_notes": ["服务变化快，采用前要复核。"],
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            output_path = tmp_path / "organize.json"

            exit_code = linuxdo_surf.main(
                [
                    "knowledge-organize-existing",
                    "--config",
                    str(config_path),
                    "--input",
                    str(readings_path),
                    "--top-per-category",
                    "5",
                    "--output",
                    str(output_path),
                ]
            )
            result = json.loads(output_path.read_text(encoding="utf-8"))
            guide_text = (config.obsidian_vault_path / "00_Home" / "怎么读这个知识库.md").read_text(encoding="utf-8")
            overview_text = (
                config.obsidian_vault_path / "10_Catalog" / "categories" / "分类总览.md"
            ).read_text(encoding="utf-8")
            workflow_comparison = (
                config.obsidian_vault_path / "10_Catalog" / "comparisons" / "AI-Coding-Workflow-选型.md"
            ).read_text(encoding="utf-8")
            resource_map = (
                config.obsidian_vault_path / "10_Catalog" / "categories" / "资源类型地图.md"
            ).read_text(encoding="utf-8")
            review_text = (
                config.obsidian_vault_path / "90_Inbox" / "review-queue" / "需要回原文复核.md"
            ).read_text(encoding="utf-8")
            manual_text = (config.obsidian_vault_path / "00_Home" / "全库带读手册.md").read_text(encoding="utf-8")
            maintenance_text = (config.obsidian_vault_path / "00_Home" / "维护状态.md").read_text(encoding="utf-8")
            watchlist_text = (
                config.obsidian_vault_path / "30_Feedback" / "decisions" / "Watchlist-使用规则.md"
            ).read_text(encoding="utf-8")
            preference_text = (
                config.obsidian_vault_path / "30_Feedback" / "preferences" / "冲浪筛选偏好.md"
            ).read_text(encoding="utf-8")
            rejection_text = (
                config.obsidian_vault_path / "30_Feedback" / "rejections" / "低价值内容排除规则.md"
            ).read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertEqual(result["readings"], 2)
        self.assertGreaterEqual(result["category_pages"], 2)
        self.assertGreaterEqual(result["comparison_pages"], 2)
        self.assertGreaterEqual(result["review_queue_items"], 2)
        self.assertIn("[[分类总览|分类总览]]", guide_text)
        self.assertIn("[[AI-Coding-Workflow-与-Skills|AI Coding Workflow 与 Skills]]", overview_text)
        self.assertIn("[[资源类型地图|资源类型地图]]", overview_text)
        self.assertIn("Superpowers", workflow_comparison)
        self.assertIn("Superpowers", resource_map)
        self.assertIn("入口选项", workflow_comparison)
        self.assertIn("当前结论", workflow_comparison)
        self.assertIn("比较范围", workflow_comparison)
        self.assertIn("适合选择", workflow_comparison)
        self.assertIn("不适合选择", workflow_comparison)
        self.assertIn("证据与来源", workflow_comparison)
        self.assertIn("为什么", workflow_comparison)
        self.assertNotIn("讨论信号", workflow_comparison)
        self.assertNotIn("累计权重", workflow_comparison)
        self.assertNotIn("高相关", workflow_comparison)
        self.assertNotRegex(workflow_comparison, r"\.\.\.|…")
        self.assertNotIn("[[Skill|Skill]]", workflow_comparison)
        self.assertIn("变化快", review_text)
        self.assertIn("watchlist", guide_text)
        self.assertIn("想追：`watchlist: true` + `status: watching`", guide_text)
        self.assertIn("暂时不看：`watchlist: false` + `status: deprioritized`", guide_text)
        self.assertIn("明确不要：`watchlist: false` + `status: rejected`", guide_text)
        self.assertIn("其他字段由 agent 维护", guide_text)
        self.assertIn("通常不用人看", guide_text)
        self.assertIn("不做逐页索引", manual_text)
        for heading in ("## 人读页面", "## 系统底账", "## 复核队列", "## 本轮建议"):
            self.assertIn(heading, maintenance_text)
        self.assertIn("30_Feedback/decisions", manual_text)
        self.assertNotIn("[[Superpowers|Superpowers]]", manual_text)
        self.assertIn("想追：`watchlist: true` + `status: watching`", watchlist_text)
        self.assertIn("暂时不看：`watchlist: false` + `status: deprioritized`", watchlist_text)
        self.assertIn("明确不要：`watchlist: false` + `status: rejected`", watchlist_text)
        self.assertIn("其他字段由 agent 维护", watchlist_text)
        self.assertIn("`deprioritized` 是“暂时不看，但不拉黑”", watchlist_text)
        self.assertNotIn("`active`", watchlist_text)
        self.assertNotIn("`disputed`", watchlist_text)
        self.assertNotIn("`adopted`", watchlist_text)
        self.assertIn("怎么追加偏好", preference_text)
        self.assertIn("怎么表达拒绝", rejection_text)
        for name, text in (
            ("guide", guide_text),
            ("overview", overview_text),
            ("workflow_comparison", workflow_comparison),
            ("resource_map", resource_map),
            ("review", review_text),
            ("manual", manual_text),
            ("maintenance", maintenance_text),
            ("watchlist", watchlist_text),
            ("preference", preference_text),
            ("rejection", rejection_text),
        ):
            assert_no_generator_residue(self, text, page_name=name)

    def test_knowledge_rewrite_needed_rewrites_candidate_from_source_extracts(self):
        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            config_path = tmp_path / "config" / "knowledge_sources.json"
            config_path.parent.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "obsidian_vault_path": str(config.obsidian_vault_path),
                        "state_root": str(config.state_root),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            candidate_dir = config.obsidian_vault_path / "10_Catalog" / "candidates"
            candidate_dir.mkdir(parents=True)
            candidate_path = candidate_dir / "Superpowers.md"
            candidate_path.write_text(
                "---\nid: resource:superpowers\ntype: candidate\nstatus: needs_rewrite\nevidence_status: legacy_summary\n---\n"
                "# Superpowers\n\n## 一句话判断\n\n高相关。\n\n## 我的反馈\n\n我偏好轻量使用\n",
                encoding="utf-8",
            )
            readings_path = tmp_path / "readings_all.json"
            readings_path.write_text(
                json.dumps(
                    {
                        "readings": [
                            {
                                "id": 30,
                                "title": "Superpowers 和 Trellis 怎么选",
                                "url": "https://linux.do/t/topic/30",
                                "summary": "讨论 Superpowers、Trellis 和 grill-me 的任务重量路由。",
                                "value_tag": "high",
                                "tools": ["Superpowers", "Trellis", "grill-me"],
                                "positive_feedback": ["Superpowers 有完整工程纪律。"],
                                "negative_feedback": ["小任务偏重。"],
                                "risk_notes": ["默认全开会增加 token 成本。"],
                                "comparison_notes": ["Trellis 更偏长任务接力，grill-me 更偏需求澄清。"],
                                "visible_post_count": 80,
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            output_path = tmp_path / "rewrite.json"

            exit_code = linuxdo_surf.main(
                [
                    "knowledge-rewrite-needed",
                    "--config",
                    str(config_path),
                    "--input",
                    str(readings_path),
                    "--output",
                    str(output_path),
                ]
            )
            result = json.loads(output_path.read_text(encoding="utf-8"))
            moved_text = candidate_path.read_text(encoding="utf-8")
            target_path = config.obsidian_vault_path / "10_Catalog" / "workflows" / "Superpowers.md"
            text = target_path.read_text(encoding="utf-8") if target_path.exists() else ""

        self.assertEqual(exit_code, 0)
        self.assertEqual(result["rewritten_pages"], 1)
        self.assertEqual(result["moved_pages"], 1)
        self.assertIn("status: moved", moved_text)
        self.assertIn("status: needs_source_review", text)
        self.assertIn("type: workflow", text)
        self.assertIn("evidence_status: source_extract", text)
        self.assertIn("任务重量路由", text)
        self.assertIn("Trellis 更偏长任务接力", text)
        self.assertIn("我偏好轻量使用", text)
        self.assertNotIn("高相关", text)
        self.assertNotIn("legacy_summary", text)
        self.assertNotRegex(text, r"\.\.\.|…")

    def test_knowledge_rewrite_needed_generated_pages_strip_old_residue(self):
        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            config_path = tmp_path / "config" / "knowledge_sources.json"
            config_path.parent.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "obsidian_vault_path": str(config.obsidian_vault_path),
                        "state_root": str(config.state_root),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            candidate_dir = config.obsidian_vault_path / "10_Catalog" / "candidates"
            candidate_dir.mkdir(parents=True)
            (candidate_dir / "Demo-Tool.md").write_text(
                "---\nid: resource:demo-tool\ntype: candidate\nstatus: needs_rewrite\nevidence_status: legacy_summary\n---\n"
                "# Demo Tool\n\n## 一句话判断\n\n高相关。\n\n## 我的反馈\n\n",
                encoding="utf-8",
            )
            (candidate_dir / "No-Evidence.md").write_text(
                "---\nid: resource:no-evidence\ntype: candidate\nstatus: needs_rewrite\nevidence_status: legacy_summary\n---\n"
                "# No Evidence\n\n## 一句话判断\n\n高相关。\n\n## 我的反馈\n\n",
                encoding="utf-8",
            )
            readings_path = tmp_path / "readings_all.json"
            readings_path.write_text(
                json.dumps(
                    {
                        "readings": [
                            {
                                "id": 32,
                                "title": "Demo Tool 使用讨论",
                                "url": "https://linux.do/t/topic/32",
                                "summary": "高相关：风佬巨作 v5.0，zcf...",
                                "value_tag": "high",
                                "tools": ["Demo Tool"],
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            output_path = tmp_path / "rewrite.json"

            exit_code = linuxdo_surf.main(
                [
                    "knowledge-rewrite-needed",
                    "--config",
                    str(config_path),
                    "--input",
                    str(readings_path),
                    "--output",
                    str(output_path),
                ]
            )
            result = json.loads(output_path.read_text(encoding="utf-8"))
            generated_texts = [
                (
                    path.relative_to(config.obsidian_vault_path).as_posix(),
                    path.read_text(encoding="utf-8"),
                )
                for path in sorted(config.obsidian_vault_path.rglob("*.md"))
                if "_system" not in path.relative_to(config.obsidian_vault_path).parts
            ]

        self.assertEqual(exit_code, 0)
        self.assertEqual(result["rewritten_pages"], 1)
        self.assertEqual(result["insufficient_pages"], 1)
        for name, text in generated_texts:
            with self.subTest(name=name):
                assert_no_generator_residue(self, text, page_name=name)

    def test_knowledge_rewrite_needed_downgrades_collection_and_alias_pages(self):
        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            config_path = tmp_path / "config" / "knowledge_sources.json"
            config_path.parent.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "obsidian_vault_path": str(config.obsidian_vault_path),
                        "state_root": str(config.state_root),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            candidate_dir = config.obsidian_vault_path / "10_Catalog" / "candidates"
            candidate_dir.mkdir(parents=True)
            (candidate_dir / "公益站.md").write_text(
                "---\nid: resource:公益站\ntype: candidate\nstatus: needs_rewrite\nevidence_status: legacy_summary\n---\n"
                "# 公益站\n\n## 一句话判断\n\n高相关。\n\n## 我的反馈\n\n",
                encoding="utf-8",
            )
            (candidate_dir / "Vibe-Coding.md").write_text(
                "---\nid: resource:vibe-coding\ntype: candidate\nstatus: needs_rewrite\nevidence_status: legacy_summary\n---\n"
                "# Vibe-Coding\n\n## 一句话判断\n\n高相关。\n\n## 我的反馈\n\n保留\n",
                encoding="utf-8",
            )
            readings_path = tmp_path / "readings_all.json"
            readings_path.write_text(
                json.dumps(
                    {
                        "readings": [
                            {
                                "id": 31,
                                "title": "公益站列表和风险",
                                "url": "https://linux.do/t/topic/31",
                                "summary": "讨论公益站列表、可用状态和服务波动。",
                                "value_tag": "high",
                                "tools": ["公益站", "API 中转"],
                                "risk_notes": ["服务变化快，采用前要复核。"],
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            output_path = tmp_path / "rewrite.json"

            exit_code = linuxdo_surf.main(
                [
                    "knowledge-rewrite-needed",
                    "--config",
                    str(config_path),
                    "--input",
                    str(readings_path),
                    "--output",
                    str(output_path),
                ]
            )
            public_moved_text = (candidate_dir / "公益站.md").read_text(encoding="utf-8")
            public_text = (
                config.obsidian_vault_path / "10_Catalog" / "collections" / "公益站.md"
            ).read_text(encoding="utf-8")
            alias_text = (candidate_dir / "Vibe-Coding.md").read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertIn("status: moved", public_moved_text)
        self.assertIn("type: collection", public_text)
        self.assertIn("集合入口", public_text)
        self.assertIn("不适合作为单一推荐结论", public_text)
        self.assertIn("status: duplicate", alias_text)
        self.assertIn("[[vibecoding|Vibecoding]]", alias_text)
        self.assertIn("保留", alias_text)
        for text in (public_moved_text, public_text, alias_text):
            self.assertNotIn("高相关", text)
            self.assertNotIn("legacy_summary", text)
            self.assertNotRegex(text, r"\.\.\.|…")

    def test_knowledge_repair_structure_moves_misplaced_pages(self):
        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            config_path = tmp_path / "config" / "knowledge_sources.json"
            config_path.parent.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "obsidian_vault_path": str(config.obsidian_vault_path),
                        "state_root": str(config.state_root),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            resource_dir = config.obsidian_vault_path / "10_Catalog" / "resources"
            collection_dir = config.obsidian_vault_path / "10_Catalog" / "collections"
            resource_dir.mkdir(parents=True)
            collection_dir.mkdir(parents=True)
            (resource_dir / "Context-Engineering.md").write_text(
                "---\nid: resource:context-engineering\ntype: resource\nstatus: watching\n---\n"
                "# Context Engineering\n\n## 我的反馈\n\n",
                encoding="utf-8",
            )
            (collection_dir / "OpenCode.md").write_text(
                "---\nid: resource:opencode\ntype: collection\nstatus: watching\n---\n"
                "# OpenCode\n\n## 我的反馈\n\n",
                encoding="utf-8",
            )
            output_path = tmp_path / "repair.json"

            exit_code = linuxdo_surf.main(
                [
                    "knowledge-repair-structure",
                    "--config",
                    str(config_path),
                    "--output",
                    str(output_path),
                ]
            )
            result = json.loads(output_path.read_text(encoding="utf-8"))
            concept_path = config.obsidian_vault_path / "20_Knowledge" / "concepts" / "Context-Engineering.md"
            opencode_path = config.obsidian_vault_path / "10_Catalog" / "resources" / "OpenCode.md"
            concept_text = concept_path.read_text(encoding="utf-8") if concept_path.exists() else ""
            opencode_text = opencode_path.read_text(encoding="utf-8") if opencode_path.exists() else ""

        self.assertEqual(exit_code, 0)
        self.assertEqual(result["moved_pages"], 2)
        self.assertIn("type: concept", concept_text)
        self.assertIn("type: resource", opencode_text)

    def test_rewrite_needed_sanitize_keeps_markdown_lines(self):
        from tools.linuxdo_knowledge.rewrite_needed import _sanitize

        text = _sanitize("- 第一行 zcf...\n- 第二行 风佬巨作")

        self.assertIn("- 第一行 ZCF", text)
        self.assertIn("\n- 第二行 社区教程", text)
        self.assertNotRegex(text, r"\.\.\.|…")


class StateMaintenanceTests(unittest.TestCase):
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

    def test_maintenance_deprioritizes_repeated_low_value_topics_without_loading_legacy_history(self):
        from tools.linuxdo_knowledge.state import ensure_knowledge_state, load_hot_indexes, maintain_state, save_hot_index

        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
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
                            "url": "https://linux.do/t/topic/1",
                            "status": "active",
                            "skip_count": 3,
                            "skip_reason": "纯列表收集，没有实测",
                        },
                        "2": {
                            "topic_id": 2,
                            "title": "还不该归档",
                            "status": "active",
                            "skip_count": 2,
                            "skip_reason": "证据不足",
                        },
                    }
                },
            )

            result = maintain_state(config, maintained_at="2026-06-01T12:00:00+00:00")
            indexes = load_hot_indexes(config)
            archive_log = config.state_root / "archive" / "maintenance-2026-06-01.jsonl"
            archive_page = config.obsidian_vault_path / "10_Catalog" / "archive" / "低价值列表.md"
            archive_log_exists = archive_log.exists()
            archive_page_exists = archive_page.exists()
            archive_text = archive_page.read_text(encoding="utf-8") if archive_page.exists() else ""

        self.assertEqual(result["deprioritized_topics"], 1)
        self.assertEqual(indexes["topic_index"]["topics"]["1"]["status"], "deprioritized")
        self.assertEqual(indexes["topic_index"]["topics"]["2"]["status"], "active")
        self.assertTrue(archive_log_exists)
        self.assertTrue(archive_page_exists)
        self.assertIn("纯列表收集，没有实测", archive_text)
        self.assertIn("https://linux.do/t/topic/1", archive_text)

    def test_knowledge_maintain_cli_writes_result_file(self):
        with TemporaryDirectoryPath() as tmp_path:
            config = self.knowledge_config(tmp_path)
            config_path = tmp_path / "config" / "knowledge_sources.json"
            config_path.parent.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "obsidian_vault_path": str(config.obsidian_vault_path),
                        "state_root": str(config.state_root),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            output_path = tmp_path / "maintain.json"

            exit_code = linuxdo_surf.main(
                [
                    "knowledge-maintain",
                    "--config",
                    str(config_path),
                    "--output",
                    str(output_path),
                ]
            )
            result = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(result, {"deprioritized_topics": 0})
