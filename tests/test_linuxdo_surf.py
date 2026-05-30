import importlib.util
import json
import unittest
from pathlib import Path
from datetime import datetime as RealDatetime
from unittest.mock import patch


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

    def test_validate_channel_rejects_unknown_channel(self):
        with self.assertRaisesRegex(ValueError, "未知操控通道"):
            linuxdo_surf.validate_channel("daily")

    def test_validate_channel_rejects_computer_use_for_normal_reading(self):
        with self.assertRaisesRegex(ValueError, "未知操控通道"):
            linuxdo_surf.validate_channel("computer-use")

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
            },
        )

    def test_save_state_normalizes_topic_ids_and_skill_names(self):
        with TemporaryDirectoryPath() as tmp_path:
            path = tmp_path / "state.json"

            linuxdo_surf.save_state(
                path,
                {
                    "read_topic_ids": [3, "2", 3],
                    "synced_skill_names": ["A", "a", "B"],
                    "reviewed_github_repos": [
                        "https://github.com/openai/codex",
                        "OpenAI/Codex",
                        "bad value",
                    ],
                    "reviewed_github_searches": ["codex skill", "Codex Skill"],
                },
            )

            saved = linuxdo_surf.load_state(path)

        self.assertEqual(saved["read_topic_ids"], [2, 3])
        self.assertEqual(saved["synced_skill_names"], ["A", "B"])
        self.assertEqual(saved["reviewed_github_repos"], ["openai/codex"])
        self.assertEqual(saved["reviewed_github_searches"], ["codex skill"])

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

    def test_build_goal_task_keeps_browser_reading_explicit(self):
        task = linuxdo_surf.build_goal_task(
            mode="goldmine",
            query="",
            frontier_path=Path("state/linuxdo_frontier_queue.json"),
            state_path=Path("state/linuxdo_surf_state.json"),
            output_path=Path("output/linuxdo_surf"),
            next_batch=[],
            max_topics=3,
            max_replies=5,
        )

        self.assertEqual(task["control_channel"], "mac-goal")
        self.assertIn("Codex 内置浏览器", task["instructions"])
        self.assertIn("/goal", task["instructions"])

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

    def test_extract_discovery_items_builds_github_repo_and_search_queues(self):
        readings = [
            {
                "id": 11,
                "url": "https://linux.do/t/topic/11",
                "title": "Codex repo",
                "summary": "推荐研究 https://github.com/openai/codex 和 workflow-kit。",
                "tools": ["workflow-kit"],
                "positive_feedback": ["README 清楚"],
                "high_value_replies": [
                    {
                        "id": 101,
                        "author": "bob",
                        "links": ["https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem"],
                    }
                ],
            }
        ]

        discovery = linuxdo_surf.extract_discovery_items(readings)

        self.assertEqual(
            [item["repo"] for item in discovery["github-repo-research"]],
            ["openai/codex", "modelcontextprotocol/servers"],
        )
        self.assertEqual(discovery["github-repo-research"][0]["source_topic_ids"], [11])
        self.assertEqual(discovery["github-repo-research"][0]["source_urls"], ["https://linux.do/t/topic/11"])
        self.assertIn("README", discovery["github-repo-research"][0]["focus"])
        self.assertEqual(discovery["github-search"][0]["query"], "workflow-kit")
        self.assertEqual(discovery["github-search"][0]["source_tool"], "workflow-kit")

    def test_github_repo_extraction_ignores_bare_paths_with_extra_segments(self):
        repos = linuxdo_surf._github_repos_from_values(
            [
                "openai/codex",
                "not/repo/path",
                "https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem",
                "https://linux.do/t/topic/11",
            ]
        )

        self.assertEqual(repos, ["openai/codex", "modelcontextprotocol/servers"])

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

    def test_cli_goal_plan_preserves_existing_discovery_queues(self):
        with TemporaryDirectoryPath() as tmp_path:
            topics_path = tmp_path / "topics.json"
            topics_path.write_text(
                json.dumps({"topics": [{"id": 1, "title": "Codex workflow", "first_text": "workflow", "views": 10}]}),
                encoding="utf-8",
            )
            queue_path = tmp_path / "frontier.json"
            queue_path.write_text(
                json.dumps(
                    {
                        "queues": {"new": [], "active-old": [], "low-traffic": []},
                        "discovery_queues": {
                            "author-tracking": [{"username": "alice", "source_topic_ids": [9], "score": 1}],
                            "comment-reference": [],
                            "tool-lookup": [{"name": "workflow-kit", "source_topic_ids": [9], "evidence_count": 1}],
                        },
                        "quotas": {"new": 0.4, "active-old": 0.4, "low-traffic": 0.2},
                    }
                ),
                encoding="utf-8",
            )
            out_dir = tmp_path / "out"

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
                    str(tmp_path / "state.json"),
                    "--queue",
                    str(queue_path),
                    "--max-topics",
                    "1",
                ]
            )

            frontier = json.loads(queue_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(frontier["discovery_queues"]["author-tracking"][0]["username"], "alice")
        self.assertEqual(frontier["discovery_queues"]["tool-lookup"][0]["name"], "workflow-kit")

    def test_cli_goal_plan_extends_next_batch_from_discovery_queues(self):
        with TemporaryDirectoryPath() as tmp_path:
            topics_path = tmp_path / "topics.json"
            topics_path.write_text(json.dumps({"topics": []}), encoding="utf-8")
            queue_path = tmp_path / "frontier.json"
            queue_path.write_text(
                json.dumps(
                    {
                        "queues": {"new": [], "active-old": [], "low-traffic": []},
                        "discovery_queues": {
                            "comment-reference": [
                                {
                                    "target_url": "https://linux.do/t/topic/30",
                                    "target_type": "linuxdo-topic",
                                    "reason": "高价值回复引用",
                                    "score": 2,
                                    "depth": 1,
                                }
                            ],
                            "tool-lookup": [],
                            "author-tracking": [],
                            "skill-workflow-evidence": [],
                        },
                        "quotas": {"new": 0.4, "active-old": 0.4, "low-traffic": 0.2},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            out_dir = tmp_path / "out"

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
                    str(tmp_path / "state.json"),
                    "--queue",
                    str(queue_path),
                    "--max-topics",
                    "1",
                ]
            )

            task = json.loads((out_dir / "goal_task_goldmine.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(task["next_batch"][0]["id"], 30)
        self.assertEqual(task["next_batch"][0]["queue"], "comment-reference")

    def test_cli_github_plan_writes_task_from_frontier_and_skips_reviewed_repos(self):
        with TemporaryDirectoryPath() as tmp_path:
            queue_path = tmp_path / "frontier.json"
            queue_path.write_text(
                json.dumps(
                    {
                        "queues": {"new": [], "active-old": [], "low-traffic": []},
                        "discovery_queues": {
                            "github-repo-research": [
                                {"repo": "openai/codex", "url": "https://github.com/openai/codex", "score": 5},
                                {"repo": "modelcontextprotocol/servers", "url": "https://github.com/modelcontextprotocol/servers", "score": 3},
                            ],
                            "github-search": [
                                {"query": "codex skill", "source_tool": "codex skill", "score": 2},
                                {"query": "workflow-kit", "source_tool": "workflow-kit", "score": 1},
                            ],
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            state_path = tmp_path / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "reviewed_github_repos": ["openai/codex"],
                        "reviewed_github_searches": ["codex skill"],
                    }
                ),
                encoding="utf-8",
            )
            out_dir = tmp_path / "out"

            exit_code = linuxdo_surf.main(
                [
                    "github-plan",
                    "--mode",
                    "discover",
                    "--query",
                    "AI coding workflow",
                    "--queue",
                    str(queue_path),
                    "--state",
                    str(state_path),
                    "--output",
                    str(out_dir),
                    "--max-repos",
                    "3",
                    "--max-searches",
                    "3",
                ]
            )

            task = json.loads((out_dir / "github_task_discover.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(task["control_channel"], "github-mcp")
        self.assertEqual([item["repo"] for item in task["next_batch"]["repositories"]], ["modelcontextprotocol/servers"])
        self.assertEqual([item["query"] for item in task["next_batch"]["searches"]], ["workflow-kit"])
        self.assertIn("GitHub MCP", task["instructions"])

    def test_cli_github_result_updates_state_and_merges_followup_repos(self):
        with TemporaryDirectoryPath() as tmp_path:
            queue_path = tmp_path / "frontier.json"
            queue_path.write_text(
                json.dumps(
                    {
                        "queues": {"new": [], "active-old": [], "low-traffic": []},
                        "discovery_queues": {
                            "github-repo-research": [],
                            "github-search": [],
                        },
                    }
                ),
                encoding="utf-8",
            )
            task_path = tmp_path / "github_task_discover.json"
            task_path.write_text(
                json.dumps(
                    {
                        "mode": "discover",
                        "query": "workflow",
                        "frontier_queue": str(queue_path),
                        "next_batch": {"repositories": [{"repo": "openai/codex"}], "searches": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            readings_path = tmp_path / "github_readings.json"
            readings_path.write_text(
                json.dumps(
                    {
                        "github_readings": [
                            {
                                "repo": "openai/codex",
                                "url": "https://github.com/openai/codex",
                                "summary": "CLI 活跃，README 清楚。",
                                "stars": 100000,
                                "last_commit_at": "2026-05-30T00:00:00Z",
                                "positive_signals": ["活跃维护"],
                                "risk_notes": ["需要本地环境"],
                                "related_repos": ["https://github.com/openai/openai-python"],
                                "related_tools": ["openai-python"],
                                "recommendation": "收藏观察",
                                "confidence": "medium",
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
                    "github-result",
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

            result = json.loads((out_dir / "github_result_discover.json").read_text(encoding="utf-8"))
            state = json.loads(state_path.read_text(encoding="utf-8"))
            frontier = json.loads(queue_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(result["reviewed_github_repos"], ["openai/codex"])
        self.assertEqual(result["items"][0]["recommendation"], "收藏观察")
        self.assertEqual(state["reviewed_github_repos"], ["openai/codex"])
        self.assertEqual(frontier["discovery_queues"]["github-repo-research"][0]["repo"], "openai/openai-python")
        self.assertEqual(frontier["discovery_queues"]["github-search"][0]["query"], "openai-python")

    def test_cli_github_result_filters_to_task_repos_and_search_queries(self):
        with TemporaryDirectoryPath() as tmp_path:
            task_path = tmp_path / "github_task_discover.json"
            task_path.write_text(
                json.dumps(
                    {
                        "mode": "discover",
                        "query": "workflow",
                        "next_batch": {
                            "repositories": [{"repo": "openai/codex"}],
                            "searches": [{"query": "workflow-kit"}],
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            readings_path = tmp_path / "github_readings.json"
            readings_path.write_text(
                json.dumps(
                    {
                        "github_readings": [
                            {"repo": "openai/codex", "summary": "任务内仓库"},
                            {"repo": "anthropic/claude-code", "summary": "混入的非任务仓库"},
                            {"repo": "acme/workflow-kit", "source_query": "workflow-kit", "summary": "任务内搜索结果"},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            out_dir = tmp_path / "out"

            exit_code = linuxdo_surf.main(
                [
                    "github-result",
                    "--task",
                    str(task_path),
                    "--readings",
                    str(readings_path),
                    "--output",
                    str(out_dir),
                    "--state",
                    str(tmp_path / "state.json"),
                ]
            )

            result = json.loads((out_dir / "github_result_discover.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(result["reviewed_github_repos"], ["openai/codex", "acme/workflow-kit"])
        self.assertEqual(result["items"][1]["source_query"], "workflow-kit")

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

    def test_cli_session_writes_session_record_and_updates_state(self):
        with TemporaryDirectoryPath() as tmp_path:
            task_path = tmp_path / "goal_task_goldmine.json"
            task_path.write_text(
                json.dumps({"mode": "goldmine", "query": "", "next_batch": [{"id": 10}]}),
                encoding="utf-8",
            )
            readings_path = tmp_path / "readings.json"
            readings_path.write_text(
                json.dumps(
                    {"readings": [{"id": 10, "title": "工具讨论", "summary": "推荐 workflow-kit", "tools": ["workflow-kit"]}]}
                ),
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

    def test_cli_session_filters_readings_to_next_batch(self):
        with TemporaryDirectoryPath() as tmp_path:
            task_path = tmp_path / "goal_task_goldmine.json"
            task_path.write_text(
                json.dumps({"mode": "goldmine", "query": "", "next_batch": [{"id": 2}]}),
                encoding="utf-8",
            )
            readings_path = tmp_path / "readings.json"
            readings_path.write_text(
                json.dumps(
                    {
                        "readings": [
                            {"id": 2, "title": "候选", "summary": "有效"},
                            {"id": 99, "title": "混入旧帖", "summary": "不该写入"},
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

            session_file = next(out_dir.glob("session_goldmine_*.json"))
            session = json.loads(session_file.read_text(encoding="utf-8"))
            state = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual([item["id"] for item in session["items"]], [2])
        self.assertEqual(state["read_topic_ids"], [2])

    def test_cli_session_preserves_context_and_merges_discovery_into_frontier(self):
        with TemporaryDirectoryPath() as tmp_path:
            queue_path = tmp_path / "frontier.json"
            queue_path.write_text(
                json.dumps(
                    {
                        "queues": {"new": [], "active-old": [], "low-traffic": []},
                        "discovery_queues": {"author-tracking": [], "comment-reference": [], "tool-lookup": []},
                        "quotas": {"new": 0.4, "active-old": 0.4, "low-traffic": 0.2},
                    }
                ),
                encoding="utf-8",
            )
            task_path = tmp_path / "goal_task_goldmine.json"
            task_path.write_text(
                json.dumps({"mode": "goldmine", "query": "", "frontier_queue": str(queue_path), "next_batch": [{"id": 10}]}),
                encoding="utf-8",
            )
            readings_path = tmp_path / "readings.json"
            readings_path.write_text(
                json.dumps(
                    {
                        "readings": [
                            {
                                "id": 10,
                                "title": "老帖更新",
                                "url": "https://linux.do/t/topic/10",
                                "author": "alice",
                                "summary": "推荐 Cursor 和 Claude Code，也提到 workflow-kit。",
                                "tools": ["workflow-kit"],
                                "first_post": "首帖经验",
                                "historical_replies": [{"id": 20, "text": "历史关键回复"}],
                                "recent_replies": [{"id": 21, "text": "近期新回复"}],
                                "high_value_replies": [
                                    {"id": 22, "text": "参考 https://linux.do/t/topic/30 和 workflow-kit", "author": "bob"}
                                ],
                                "follow_up_links": ["https://linux.do/t/topic/30"],
                                "confidence": "medium",
                                "positive_feedback": ["好用"],
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
                    "session",
                    "--task",
                    str(task_path),
                    "--readings",
                    str(readings_path),
                    "--output",
                    str(out_dir),
                    "--state",
                    str(tmp_path / "state.json"),
                    "--stop-reason",
                    "达到本轮深读预算",
                ]
            )

            session_file = next(out_dir.glob("session_goldmine_*.json"))
            session = json.loads(session_file.read_text(encoding="utf-8"))
            frontier = json.loads(queue_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        item = session["items"][0]
        self.assertEqual(item["author"], "alice")
        self.assertEqual(item["first_post"], "首帖经验")
        self.assertEqual(item["historical_replies"][0]["id"], 20)
        self.assertEqual(item["recent_replies"][0]["id"], 21)
        self.assertEqual(item["high_value_replies"][0]["id"], 22)
        self.assertEqual(item["follow_up_links"], ["https://linux.do/t/topic/30"])
        self.assertEqual(item["confidence"], "medium")
        self.assertEqual(frontier["discovery_queues"]["author-tracking"][0]["username"], "alice")
        self.assertEqual(frontier["discovery_queues"]["comment-reference"][0]["target_type"], "linuxdo-topic")
        self.assertEqual(frontier["discovery_queues"]["comment-reference"][0]["depth"], 1)
        self.assertEqual(
            [item["name"] for item in frontier["discovery_queues"]["tool-lookup"]],
            ["workflow-kit", "Cursor", "Claude Code"],
        )

    def test_extract_discovery_items_merges_author_and_tool_evidence(self):
        readings = [
            {
                "id": 1,
                "url": "https://linux.do/t/topic/1",
                "author": "alice",
                "summary": "Cursor 很顺手。",
                "positive_feedback": ["稳定"],
            },
            {
                "id": 2,
                "url": "https://linux.do/t/topic/2",
                "author": "alice",
                "summary": "Cursor 也有上下文成本。",
                "negative_feedback": ["贵"],
            },
        ]

        discovery = linuxdo_surf.extract_discovery_items(readings)

        author = discovery["author-tracking"][0]
        tool = discovery["tool-lookup"][0]
        self.assertEqual(author["source_topic_ids"], [1, 2])
        self.assertEqual(author["score"], 2)
        self.assertEqual(tool["name"], "Cursor")
        self.assertEqual(tool["source_topic_ids"], [1, 2])
        self.assertEqual(tool["evidence_count"], 2)
        self.assertEqual(tool["positive_count"], 1)
        self.assertEqual(tool["negative_count"], 1)

    def test_extract_discovery_items_uses_follow_up_links_and_reply_links(self):
        readings = [
            {
                "id": 10,
                "url": "https://linux.do/t/topic/10",
                "follow_up_links": ["https://linux.do/t/topic/31"],
                "high_value_replies": [
                    {"id": 22, "links": ["https://linux.do/t/topic/32"], "text": "见另一个帖子"}
                ],
            }
        ]

        discovery = linuxdo_surf.extract_discovery_items(readings)

        self.assertEqual(
            [item["target_url"] for item in discovery["comment-reference"]],
            ["https://linux.do/t/topic/31", "https://linux.do/t/topic/32"],
        )

    def test_extract_discovery_items_counts_string_feedback_as_one_item(self):
        readings = [
            {
                "id": 1,
                "url": "https://linux.do/t/topic/1",
                "summary": "workflow-kit 很顺手。",
                "tools": ["workflow-kit"],
                "positive_feedback": "好用",
                "negative_feedback": "贵",
            }
        ]

        discovery = linuxdo_surf.extract_discovery_items(readings)

        tool = discovery["tool-lookup"][0]
        self.assertEqual(tool["positive_count"], 1)
        self.assertEqual(tool["negative_count"], 1)

    def test_cli_session_does_not_overwrite_same_second_records(self):
        class FixedDatetime:
            @staticmethod
            def now():
                return RealDatetime(2026, 5, 31, 12, 0, 0, 123456)

        with TemporaryDirectoryPath() as tmp_path:
            task_path = tmp_path / "goal_task_goldmine.json"
            task_path.write_text(
                json.dumps({"mode": "goldmine", "query": "", "next_batch": [{"id": 10}]}),
                encoding="utf-8",
            )
            readings_path = tmp_path / "readings.json"
            readings_path.write_text(
                json.dumps({"readings": [{"id": 10, "title": "工具讨论", "summary": "推荐 workflow-kit"}]}),
                encoding="utf-8",
            )
            out_dir = tmp_path / "out"

            with patch.object(linuxdo_surf, "datetime", FixedDatetime):
                first = linuxdo_surf.main(
                    [
                        "session",
                        "--task",
                        str(task_path),
                        "--readings",
                        str(readings_path),
                        "--output",
                        str(out_dir),
                        "--state",
                        str(tmp_path / "state.json"),
                        "--stop-reason",
                        "达到本轮深读预算",
                    ]
                )
                second = linuxdo_surf.main(
                    [
                        "session",
                        "--task",
                        str(task_path),
                        "--readings",
                        str(readings_path),
                        "--output",
                        str(out_dir),
                        "--state",
                        str(tmp_path / "state.json"),
                        "--stop-reason",
                        "达到本轮深读预算",
                    ]
                )

            session_files = list(out_dir.glob("session_goldmine_*.json"))

        self.assertEqual(first, 0)
        self.assertEqual(second, 0)
        self.assertEqual(len(session_files), 2)

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
