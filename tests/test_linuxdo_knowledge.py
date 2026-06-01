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

    def test_ensure_knowledge_state_creates_hot_indexes_and_directories(self):
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
