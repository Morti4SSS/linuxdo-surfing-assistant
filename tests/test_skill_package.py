import re
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LinuxdoSurfingSkillPackageTests(unittest.TestCase):
    def test_root_skill_declares_browser_first_continuous_surfing_workflow(self):
        skill_path = ROOT / "SKILL.md"

        text = skill_path.read_text(encoding="utf-8")

        self.assertIn("name: linuxdo-surfing", text)
        self.assertRegex(text, r"description: .*(Linux\.do|linux\.do)")
        self.assertIn("Codex 内置浏览器", text)
        self.assertIn("GitHub", text)
        self.assertIn("github-plan", text)
        self.assertIn("github-result", text)
        self.assertIn("backfill-plan", text)
        self.assertIn("linuxdo-only", text)
        self.assertIn("github-only", text)
        self.assertIn("linuxdo-first", text)
        self.assertIn("github-first", text)
        self.assertIn("/goal", text)
        self.assertIn("持续迭代", text)
        self.assertIn("延展冲浪", text)
        self.assertIn("切换热度排序", text)
        self.assertIn("切换最新排序", text)
        self.assertIn("同义词", text)
        self.assertIn("tools/linuxdo_surf.py", text)
        self.assertIn("状态脚本", text)
        self.assertIn("不是主体", text)
        self.assertIn("one-screen brief", text)
        self.assertIn("马上试", text)
        self.assertIn("收藏观察", text)
        self.assertIn("暂时跳过", text)
        self.assertIn("decision brief", text)
        self.assertIn("read-post index", text)
        self.assertIn("发现状态", text)
        self.assertIn("展开第 2 个工具的优劣", text)

    def test_skill_references_cover_reading_schema_and_continuous_loop(self):
        expected = [
            "references/reading-schema.md",
            "references/continuous-loop.md",
            "references/surfing-modes.md",
            "references/skill-evidence.md",
            "references/linuxdo-reading-playbook.md",
            "references/github-research.md",
        ]

        for relative_path in expected:
            path = ROOT / relative_path
            with self.subTest(path=relative_path):
                self.assertTrue(path.exists(), f"{relative_path} should exist")
                text = path.read_text(encoding="utf-8")
                self.assertGreater(len(re.sub(r"\s+", "", text)), 200)

    def test_references_preserve_absorption_friendly_output_contract(self):
        reading_schema = (ROOT / "references" / "reading-schema.md").read_text(encoding="utf-8")
        continuous_loop = (ROOT / "references" / "continuous-loop.md").read_text(encoding="utf-8")
        surfing_modes = (ROOT / "references" / "surfing-modes.md").read_text(encoding="utf-8")

        for text in [reading_schema, continuous_loop, surfing_modes]:
            with self.subTest():
                self.assertIn("3-5", text)
                self.assertIn("马上试", text)
                self.assertIn("收藏观察", text)
                self.assertIn("暂时跳过", text)

        self.assertIn("Chat Compression", reading_schema)
        self.assertIn("Checkpoint Output", continuous_loop)
        self.assertIn("Default User-Facing Output", surfing_modes)
        self.assertIn("session/evidence files", surfing_modes)
        self.assertIn("每个读过的帖子", reading_schema)
        self.assertIn("已读帖子索引", continuous_loop)
        self.assertIn("已读帖子索引", surfing_modes)

    def test_references_cover_github_research_loop(self):
        github_research = (ROOT / "references" / "github-research.md").read_text(encoding="utf-8")
        continuous_loop = (ROOT / "references" / "continuous-loop.md").read_text(encoding="utf-8")
        reading_schema = (ROOT / "references" / "reading-schema.md").read_text(encoding="utf-8")
        skill_evidence = (ROOT / "references" / "skill-evidence.md").read_text(encoding="utf-8")

        self.assertIn("GitHub is an evidence and extension source", github_research)
        self.assertIn("github_readings", github_research)
        self.assertIn("Strategy Modes", github_research)
        self.assertIn("backfill-plan", github_research)
        self.assertIn("heavy `hybrid`", github_research)
        self.assertIn("github-repo-research", continuous_loop)
        self.assertIn("github-search", continuous_loop)
        self.assertIn("github_repos", reading_schema)
        self.assertIn("GitHub health signals", skill_evidence)

    def test_openai_yaml_matches_skill_identity(self):
        config_path = ROOT / "agents" / "openai.yaml"

        text = config_path.read_text(encoding="utf-8")

        self.assertIn('display_name: "Linux.do Surfing"', text)
        self.assertIn('default_prompt: "Use $linuxdo-surfing', text)
        self.assertIn("allow_implicit_invocation: true", text)

    def test_scripts_entrypoint_delegates_to_state_helper(self):
        script_path = ROOT / "scripts" / "linuxdo_surf.py"

        result = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("Linux.do", result.stdout)
        self.assertIn("goal-plan", result.stdout)


if __name__ == "__main__":
    unittest.main()
