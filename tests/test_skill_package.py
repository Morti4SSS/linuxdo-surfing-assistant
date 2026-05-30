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
        self.assertIn("/goal", text)
        self.assertIn("持续迭代", text)
        self.assertIn("延展冲浪", text)
        self.assertIn("tools/linuxdo_surf.py", text)
        self.assertIn("状态脚本", text)
        self.assertIn("不是主体", text)

    def test_skill_references_cover_reading_schema_and_continuous_loop(self):
        expected = [
            "references/reading-schema.md",
            "references/continuous-loop.md",
            "references/surfing-modes.md",
            "references/skill-evidence.md",
        ]

        for relative_path in expected:
            path = ROOT / relative_path
            with self.subTest(path=relative_path):
                self.assertTrue(path.exists(), f"{relative_path} should exist")
                text = path.read_text(encoding="utf-8")
                self.assertGreater(len(re.sub(r"\s+", "", text)), 200)

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
