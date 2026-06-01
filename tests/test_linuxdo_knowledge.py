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
