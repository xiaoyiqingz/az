import tempfile
import unittest
from pathlib import Path

from pydantic_ai_skills import SkillsToolset

from config.settings import load_settings
from tools.skills import get_skills_dir


class TestSkillsToolset(unittest.TestCase):
    def test_get_skills_dir_prefers_env_value(self):
        settings = load_settings({"SKILLS_DIR": "./custom-skills"})
        skills_dir = get_skills_dir(settings)
        self.assertTrue(str(skills_dir).endswith("custom-skills"))

    def test_default_skills_dir_uses_az_home(self):
        settings = load_settings({"AZ_HOME": "/tmp/az-home"})
        self.assertEqual(
            str(get_skills_dir(settings)),
            "/tmp/az-home/skills",
        )

    def test_skills_toolset_loads_standard_skill_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            skills_root = Path(tmp_dir) / "skills"
            skill_dir = skills_root / "demo-skill"
            (skill_dir / "resources").mkdir(parents=True)
            (skill_dir / "scripts").mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: demo-skill\ndescription: demo description\n---\n\n# Demo Skill\n",
                encoding="utf-8",
            )
            (skill_dir / "REFERENCE.md").write_text("# Ref\n", encoding="utf-8")
            (skill_dir / "scripts" / "hello.py").write_text(
                "print('hello')\n",
                encoding="utf-8",
            )

            toolset = SkillsToolset(directories=[skills_root])
            self.assertIn("demo-skill", toolset.skills)

            skill = toolset.skills["demo-skill"]
            resource_names = sorted(resource.name for resource in skill.resources)
            script_names = sorted(script.name for script in skill.scripts)

            self.assertIn("REFERENCE.md", resource_names)
            self.assertIn("scripts/hello.py", script_names)


if __name__ == "__main__":
    unittest.main()
