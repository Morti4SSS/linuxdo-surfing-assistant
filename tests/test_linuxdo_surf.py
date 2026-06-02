import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "linuxdo_surf.py"
spec = importlib.util.spec_from_file_location("linuxdo_surf", MODULE_PATH)
linuxdo_surf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(linuxdo_surf)


class LinuxdoSurfTests(unittest.TestCase):
    def test_validate_mode_accepts_four_modes(self):
        self.assertEqual(linuxdo_surf.validate_mode("research"), "research")
        self.assertEqual(linuxdo_surf.validate_mode("goldmine"), "goldmine")
        self.assertEqual(linuxdo_surf.validate_mode("skill-feedback"), "skill-feedback")
        self.assertEqual(linuxdo_surf.validate_mode("discover"), "discover")

    def test_validate_mode_rejects_unknown_mode(self):
        with self.assertRaisesRegex(ValueError, "未知模式"):
            linuxdo_surf.validate_mode("daily")

    def test_validate_channel_accepts_supported_channels(self):
        self.assertEqual(linuxdo_surf.validate_channel("codex-browser"), "codex-browser")
        self.assertEqual(linuxdo_surf.validate_channel("user-chrome"), "user-chrome")
        self.assertEqual(linuxdo_surf.validate_channel("mac-goal"), "mac-goal")
        self.assertEqual(linuxdo_surf.validate_channel("computer-use"), "computer-use")

    def test_validate_channel_rejects_unknown_channel(self):
        with self.assertRaisesRegex(ValueError, "未知操控通道"):
            linuxdo_surf.validate_channel("daily")

    def test_rank_topics_prefers_query_matches_and_skips_read_ids(self):
        topics = [
            {"id": 1, "title": "普通闲聊", "first_text": "没有重点", "like_count": 50, "reply_count": 20, "views": 1000},
            {"id": 2, "title": "Codex 长任务工作流经验", "first_text": "讨论 codex workflow skill", "like_count": 5, "reply_count": 2, "views": 100},
            {"id": 3, "title": "Codex skill 路由", "first_text": "skill 管理和工作流", "like_count": 1, "reply_count": 1, "views": 50},
        ]

        ranked = linuxdo_surf.rank_topics(topics, mode="research", query="Codex 工作流", read_ids={3}, limit=5)

        self.assertEqual([item["id"] for item in ranked], [2, 1])
        self.assertGreater(ranked[0]["surf_score"], ranked[1]["surf_score"])

    def test_rank_topics_ignores_non_numeric_topic_ids(self):
        topics = [
            {"id": "abc", "title": "坏数据", "first_text": "Codex 工作流", "like_count": 10},
            {"id": "2", "title": "Codex 工作流", "first_text": "有效数据", "like_count": 1},
        ]

        ranked = linuxdo_surf.rank_topics(topics, mode="research", query="Codex")

        self.assertEqual([item["id"] for item in ranked], ["2"])

    def test_load_state_returns_default_when_missing(self):
        with TemporaryDirectoryPath() as tmp_path:
            state = linuxdo_surf.load_state(tmp_path / "missing.json")

        self.assertEqual(
            state,
            {
                "read_topic_ids": [],
                "synced_skill_names": [],
                "reviewed_github_repos": [],
                "reviewed_github_searches": [],
                "render_checked_topic_ids": [],
            },
        )

    def test_save_state_normalizes_topic_ids_and_skill_names(self):
        with TemporaryDirectoryPath() as tmp_path:
            path = tmp_path / "state.json"

            linuxdo_surf.save_state(path, {"read_topic_ids": [3, "2", 3], "synced_skill_names": ["A", "a", "B"]})

            saved = linuxdo_surf.load_state(path)

        self.assertEqual(saved["read_topic_ids"], [2, 3])
        self.assertEqual(saved["synced_skill_names"], ["A", "B"])

    def test_build_browser_task_contains_mode_budget_and_candidates(self):
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

        self.assertEqual(task["mode"], "research")
        self.assertEqual(task["query"], "Codex 工作流")
        self.assertEqual(task["budget"], {"max_topics": 3, "max_replies_per_topic": 5})
        self.assertEqual(task["candidates"][0]["id"], 2)
        self.assertIn("Codex 内置浏览器", task["instructions"])

    def test_build_browser_task_defaults_to_codex_browser_channel(self):
        task = linuxdo_surf.build_browser_task(
            mode="research",
            query="Codex 工作流",
            candidates=[],
            skill_names=[],
            max_topics=3,
            max_replies=5,
        )

        self.assertEqual(task["control_channel"], "codex-browser")
        self.assertIn("Codex 内置浏览器", task["instructions"])

    def test_build_browser_task_adds_user_chrome_channel_instructions(self):
        task = linuxdo_surf.build_browser_task(
            mode="research",
            query="Codex 工作流",
            candidates=[],
            skill_names=[],
            max_topics=3,
            max_replies=5,
            control_channel="user-chrome",
        )

        self.assertEqual(task["control_channel"], "user-chrome")
        self.assertIn("Chrome", task["instructions"])
        self.assertIn("标签组", task["instructions"])

    def test_build_mode_result_marks_read_topics_and_keeps_action_items(self):
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

        self.assertEqual(result["mode"], "research")
        self.assertEqual(result["read_topic_ids"], [2])
        self.assertEqual(result["items"][0]["action_items"], ["把 handoff 写进工作流"])
        self.assertEqual(result["mode_summary"]["research_focus"], "Codex 工作流")

    def test_build_mode_result_adds_goldmine_summary_fields(self):
        task = {"mode": "goldmine", "query": "", "candidates": []}
        readings = [
            {
                "id": 3,
                "title": "新工具讨论",
                "url": "https://linux.do/t/topic/3",
                "summary": "一个值得后续追踪的新工具。",
                "action_items": ["后续追踪"],
                "tools": ["new-tool"],
            }
        ]

        result = linuxdo_surf.build_mode_result(task, readings)

        self.assertEqual(result["mode_summary"]["worth_deep_reading"], ["新工具讨论"])
        self.assertEqual(result["mode_summary"]["follow_up_candidates"], ["new-tool"])

    def test_build_mode_result_adds_discover_summary_fields(self):
        task = {"mode": "discover", "query": "", "candidates": []}
        readings = [
            {
                "id": 4,
                "title": "workflow 工具推荐",
                "url": "https://linux.do/t/topic/4",
                "summary": "推荐一个 workflow 工具。",
                "tools": ["workflow-kit"],
                "risk_notes": ["可能和现有 workflow 重复"],
            }
        ]

        result = linuxdo_surf.build_mode_result(task, readings)

        self.assertEqual(result["mode_summary"]["new_candidates"], ["workflow-kit"])
        self.assertEqual(result["mode_summary"]["needs_github_verification"], ["workflow-kit"])

    def test_build_skill_evidence_package_extracts_matching_skill_feedback(self):
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

        self.assertEqual(package["evidence"][0]["skill_name"], "skill-creator")
        self.assertEqual(package["evidence"][0]["sync_target"], "community/skill_reviews.json")
        self.assertEqual(package["evidence"][0]["topic_links"], ["https://linux.do/t/topic/10"])
        self.assertEqual(package["evidence"][0]["positive_feedback"], ["触发条件清晰很有用"])

    def test_cli_plan_writes_browser_task_and_state(self):
        with TemporaryDirectoryPath() as tmp_path:
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

            task = json.loads((out_dir / "browser_task_research.json").read_text(encoding="utf-8"))
            state_exists = state_path.exists()

        self.assertEqual(exit_code, 0)
        self.assertEqual(task["candidates"][0]["id"], 2)
        self.assertTrue(state_exists)

    def test_cli_help_includes_skill_referenced_legacy_and_knowledge_commands(self):
        parser = linuxdo_surf.build_parser()

        help_text = parser.format_help()

        for command in [
            "goal-plan",
            "session",
            "github-plan",
            "github-result",
            "backfill-plan",
            "visual-review-plan",
            "knowledge-init",
            "knowledge-plan",
            "knowledge-session",
        ]:
            with self.subTest(command=command):
                self.assertIn(command, help_text)

    def test_cli_legacy_compat_commands_write_task_artifacts(self):
        with TemporaryDirectoryPath() as tmp_path:
            out_dir = tmp_path / "out"
            state_path = tmp_path / "state.json"

            github_exit = linuxdo_surf.main(
                [
                    "github-plan",
                    "--mode",
                    "discover",
                    "--strategy",
                    "github-only",
                    "--query",
                    "codex workflow skill",
                    "--output",
                    str(out_dir),
                    "--state",
                    str(state_path),
                ]
            )
            github_task = json.loads((out_dir / "github_task_discover.json").read_text(encoding="utf-8"))

            readings_path = tmp_path / "readings.json"
            readings_path.write_text(
                json.dumps(
                    {
                        "readings": [
                            {
                                "id": 7,
                                "title": "WebUI 截图教程",
                                "url": "https://linux.do/t/topic/7",
                                "summary": "需要看截图确认 UI 状态。",
                                "render_required": True,
                                "visual_review_status": "needed",
                            },
                            {
                                "id": 8,
                                "title": "已核验",
                                "url": "https://linux.do/t/topic/8",
                                "summary": "已检查。",
                                "render_required": True,
                                "visual_review_status": "checked",
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            visual_exit = linuxdo_surf.main(
                [
                    "visual-review-plan",
                    "--input",
                    str(readings_path),
                    "--output",
                    str(out_dir),
                    "--state",
                    str(state_path),
                    "--max-topics",
                    "5",
                ]
            )
            visual_task = json.loads((out_dir / "visual_review_task.json").read_text(encoding="utf-8"))

        self.assertEqual(github_exit, 0)
        self.assertEqual(github_task["control_channel"], "github-mcp")
        self.assertEqual(github_task["next_batch"]["searches"][0]["query"], "codex workflow skill")
        self.assertEqual(visual_exit, 0)
        self.assertEqual([item["id"] for item in visual_task["items"]], [7])

    def test_scripts_entrypoint_delegates_to_tools_helper(self):
        script_path = MODULE_PATH.parents[1] / "scripts" / "linuxdo_surf.py"

        result = subprocess.run(
            [sys.executable, str(script_path), "github-plan", "--help"],
            cwd=MODULE_PATH.parents[1],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("github-plan", result.stdout)

    def test_cli_plan_writes_control_channel(self):
        with TemporaryDirectoryPath() as tmp_path:
            topics_path = tmp_path / "topics.json"
            topics_path.write_text(json.dumps({"topics": []}), encoding="utf-8")
            out_dir = tmp_path / "out"

            exit_code = linuxdo_surf.main(
                [
                    "plan",
                    "--mode",
                    "research",
                    "--channel",
                    "user-chrome",
                    "--topics",
                    str(topics_path),
                    "--output",
                    str(out_dir),
                    "--state",
                    str(tmp_path / "state.json"),
                ]
            )

            task = json.loads((out_dir / "browser_task_research.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(task["control_channel"], "user-chrome")

    def test_cli_plan_writes_research_strategy(self):
        with TemporaryDirectoryPath() as tmp_path:
            topics_path = tmp_path / "topics.json"
            topics_path.write_text(json.dumps({"topics": []}), encoding="utf-8")
            out_dir = tmp_path / "out"

            exit_code = linuxdo_surf.main(
                [
                    "plan",
                    "--mode",
                    "research",
                    "--strategy",
                    "linuxdo-first",
                    "--topics",
                    str(topics_path),
                    "--output",
                    str(out_dir),
                    "--state",
                    str(tmp_path / "state.json"),
                ]
            )

            task = json.loads((out_dir / "browser_task_research.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(task["research_strategy"], "linuxdo-first")

    def test_cli_plan_rejects_unknown_channel(self):
        with TemporaryDirectoryPath() as tmp_path:
            topics_path = tmp_path / "topics.json"
            topics_path.write_text(json.dumps({"topics": []}), encoding="utf-8")

            with self.assertRaises(SystemExit) as context:
                linuxdo_surf.main(["plan", "--mode", "research", "--channel", "bad", "--topics", str(topics_path)])

        self.assertEqual(context.exception.code, 2)

    def test_cli_evidence_writes_skill_evidence_package(self):
        with TemporaryDirectoryPath() as tmp_path:
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
            package = json.loads((out_dir / "skill_evidence_package.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(package["evidence"][0]["skill_name"], "skill-creator")

    def test_cli_bookmark_sync_writes_result(self):
        with TemporaryDirectoryPath() as tmp_path:
            config_path = tmp_path / "config" / "knowledge_sources.json"
            bookmark_path = tmp_path / "bookmarks.json"
            output_path = tmp_path / "out" / "bookmark_sync_result.json"
            config_path.parent.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "linuxdo_scripts_bookmarks": {"enabled": True, "path": str(bookmark_path)},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            bookmark_path.write_text(
                json.dumps(
                    [
                        {
                            "name": "Skills / Plugins",
                            "list": [
                                {
                                    "cate": "开发调优",
                                    "tags": ["skill"],
                                    "timestamp": 1780151443336,
                                    "title": "某 skill 讨论",
                                    "url": "https://linux.do/t/topic/2273499",
                                }
                            ],
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            exit_code = linuxdo_surf.main(
                ["bookmark-sync", "--config", str(config_path), "--output", str(output_path)]
            )
            result = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(result["new"], 1)
        self.assertEqual(result["metadata_changed"], 0)
        self.assertEqual(result["unchanged"], 0)

    def test_bookmark_sync_script_path_writes_result(self):
        with TemporaryDirectoryPath() as tmp_path:
            config_path = tmp_path / "config" / "knowledge_sources.json"
            bookmark_path = tmp_path / "bookmarks.json"
            output_path = tmp_path / "out" / "bookmark_sync_result.json"
            config_path.parent.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "linuxdo_scripts_bookmarks": {"enabled": True, "path": str(bookmark_path)},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            bookmark_path.write_text(
                json.dumps(
                    [
                        {
                            "name": "Skills / Plugins",
                            "list": [
                                {
                                    "cate": "开发调优",
                                    "tags": ["skill"],
                                    "timestamp": 1780151443336,
                                    "title": "某 skill 讨论",
                                    "url": "https://linux.do/t/topic/2273499",
                                }
                            ],
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "bookmark-sync",
                    "--config",
                    str(config_path),
                    "--output",
                    str(output_path),
                ],
                cwd=MODULE_PATH.parents[1],
                check=False,
                capture_output=True,
                text=True,
            )
            written = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(written, {"new": 1, "metadata_changed": 0, "unchanged": 0})

    def test_cli_knowledge_plan_writes_task(self):
        with TemporaryDirectoryPath() as tmp_path:
            config_path = tmp_path / "config" / "knowledge_sources.json"
            output_path = tmp_path / "out" / "knowledge_task_latest.json"
            state_root = tmp_path / "state" / "knowledge"
            config_path.parent.mkdir()
            config_path.write_text(json.dumps({"obsidian_vault_path": "vault"}, ensure_ascii=False), encoding="utf-8")
            state_root.mkdir(parents=True)
            (state_root / "frontier_queue.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "topic_id": 42,
                                "url": "https://linux.do/t/topic/42",
                                "title": "实测工具",
                                "priority": 80,
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            exit_code = linuxdo_surf.main(
                ["knowledge-plan", "--config", str(config_path), "--output", str(output_path), "--batch-size", "1"]
            )
            task = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(task["items"][0]["topic_id"], 42)
        self.assertEqual(task["items"][0]["reading_level"], 2)

    def test_cli_result_writes_mode_result_and_updates_read_state(self):
        with TemporaryDirectoryPath() as tmp_path:
            task_path = tmp_path / "browser_task_research.json"
            task_path.write_text(
                json.dumps({"mode": "research", "query": "Codex 工作流", "candidates": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            readings_path = tmp_path / "readings.json"
            readings_path.write_text(
                json.dumps(
                    {
                        "readings": [
                            {
                                "id": 2,
                                "title": "Codex 长任务工作流",
                                "url": "https://linux.do/t/topic/2",
                                "summary": "需要计划和交接。",
                                "action_items": ["写 handoff"],
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
                    "result",
                    "--task",
                    str(task_path),
                    "--readings",
                    str(readings_path),
                    "--output",
                    str(out_dir),
                    "--state",
                    str(state_path),
                ]
            )
            result = json.loads((out_dir / "mode_result_research.json").read_text(encoding="utf-8"))
            state = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(result["read_topic_ids"], [2])
        self.assertEqual(state["read_topic_ids"], [2])

    def test_cli_result_filters_readings_to_task_candidates(self):
        with TemporaryDirectoryPath() as tmp_path:
            task_path = tmp_path / "browser_task_research.json"
            task_path.write_text(
                json.dumps(
                    {
                        "mode": "research",
                        "query": "Codex 工作流",
                        "candidates": [{"id": 2, "title": "候选"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            readings_path = tmp_path / "readings.json"
            readings_path.write_text(
                json.dumps(
                    {
                        "readings": [
                            {"id": 2, "title": "候选", "url": "https://linux.do/t/topic/2", "summary": "有效"},
                            {"id": 99, "title": "混入旧帖", "url": "https://linux.do/t/topic/99", "summary": "不该写入"},
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
                    "result",
                    "--task",
                    str(task_path),
                    "--readings",
                    str(readings_path),
                    "--output",
                    str(out_dir),
                    "--state",
                    str(state_path),
                ]
            )
            result = json.loads((out_dir / "mode_result_research.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(result["read_topic_ids"], [2])
        self.assertEqual([item["id"] for item in result["items"]], [2])

    def test_cli_evidence_updates_synced_skill_state_when_state_is_given(self):
        with TemporaryDirectoryPath() as tmp_path:
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
            state_path = tmp_path / "state.json"

            exit_code = linuxdo_surf.main(
                [
                    "evidence",
                    "--skills",
                    "skill-creator",
                    "--readings",
                    str(readings_path),
                    "--output",
                    str(out_dir),
                    "--state",
                    str(state_path),
                ]
            )
            state = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(state["synced_skill_names"], ["skill-creator"])

    def test_cli_plan_requires_skills_for_skill_feedback_mode(self):
        with TemporaryDirectoryPath() as tmp_path:
            topics_path = tmp_path / "topics.json"
            topics_path.write_text(json.dumps({"topics": []}), encoding="utf-8")

            with self.assertRaises(SystemExit) as context:
                linuxdo_surf.main(
                    [
                        "plan",
                        "--mode",
                        "skill-feedback",
                        "--topics",
                        str(topics_path),
                    ]
                )

        self.assertEqual(context.exception.code, 2)

    def test_cli_plan_rejects_non_positive_budget(self):
        with TemporaryDirectoryPath() as tmp_path:
            topics_path = tmp_path / "topics.json"
            topics_path.write_text(json.dumps({"topics": []}), encoding="utf-8")

            with self.assertRaises(SystemExit) as context:
                linuxdo_surf.main(
                    [
                        "plan",
                        "--mode",
                        "research",
                        "--topics",
                        str(topics_path),
                        "--max-topics",
                        "0",
                    ]
                )

        self.assertEqual(context.exception.code, 2)

    def test_load_topics_and_readings_ignore_invalid_json_top_level(self):
        with TemporaryDirectoryPath() as tmp_path:
            topics_path = tmp_path / "topics.json"
            readings_path = tmp_path / "readings.json"
            topics_path.write_text(json.dumps("bad"), encoding="utf-8")
            readings_path.write_text(json.dumps(123), encoding="utf-8")

            topics = linuxdo_surf.load_topics(topics_path)
            readings = linuxdo_surf.load_readings(readings_path)

        self.assertEqual(topics, [])
        self.assertEqual(readings, [])

    def test_skill_evidence_does_not_match_short_name_inside_words(self):
        readings = [
            {
                "id": 5,
                "url": "https://linux.do/t/topic/5",
                "title": "goose 工具讨论",
                "summary": "goose 是另一个工具。",
                "tools": ["goose"],
            }
        ]

        package = linuxdo_surf.build_skill_evidence_package(["go"], readings)

        self.assertEqual(package["evidence"], [])


class TemporaryDirectoryPath:
    def __enter__(self):
        from tempfile import TemporaryDirectory

        self._temporary_directory = TemporaryDirectory()
        return Path(self._temporary_directory.name)

    def __exit__(self, exc_type, exc, traceback):
        self._temporary_directory.cleanup()
