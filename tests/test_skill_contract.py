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
        self.assertIn("Each skin belongs to one scene", skill)
        self.assertNotIn("/api/v1/", skill)
        self.assertIn("shared growth", skill)
        self.assertIn("star-voyage", skill)
        for action in ("configure", "neutral", "reset"):
            self.assertIn(action, skill)
        self.assertIn("yinyue-2", skill)


if __name__ == "__main__":
    unittest.main()
