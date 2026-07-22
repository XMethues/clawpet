import unittest
from pathlib import Path


class BundledSkillContractTests(unittest.TestCase):
    def test_skill_documents_the_single_command_interface_and_domain_invariants(self):
        root = Path(__file__).resolve().parents[1]
        skill = (root / "skills" / "clawchat-pet" / "SKILL.md").read_text(encoding="utf-8")
        references = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (root / "skills" / "clawchat-pet" / "references").glob("*.md")
        )

        self.assertNotIn("银月", skill + references)
        self.assertIn("prompt_personality", skill)
        self.assertIn("GET  /catalog", skill)
        self.assertIn("POST /command", skill)
        self.assertIn('"type":"select_scene"', skill)
        self.assertIn('"type":"customize_skin"', skill)
        self.assertIn("backgroundImage", skill)
        self.assertIn("without a rebuild", skill)
        self.assertIn("clawchat-pet/backgrounds", skill)
        self.assertIn("860×1600", skill)
        self.assertIn("Each skin belongs to one scene", skill)
        self.assertNotIn("/api/v1/", skill)
        self.assertIn("shared growth", skill)
        self.assertIn("star-voyage", skill)
        for action in ("configure", "neutral", "reset"):
            self.assertIn(action, skill)
        self.assertIn("yinyue-2", skill)


class ReadmeInstallationContractTests(unittest.TestCase):
    def test_readme_documents_the_enabled_plugin_install_command(self):
        root = Path(__file__).resolve().parents[1]
        readme = (root / "README.md").read_text(encoding="utf-8")

        self.assertIn("## Installation", readme)
        self.assertIn(
            "hermes plugins install XMethues/clawpet --enable",
            readme,
        )


class FrontendFailureContractTests(unittest.TestCase):
    def test_frontend_reports_presentation_failures_instead_of_showing_defaults(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "frontend" / "src" / "main.tsx").read_text(
            encoding="utf-8"
        )

        self.assertNotIn(".catch(() => {})", source)
        self.assertIn("宠物服务暂不可用", source)
        self.assertIn("请求失败：", source)


if __name__ == "__main__":
    unittest.main()
