import unittest
from pathlib import Path


class BundledSkillContractTests(unittest.TestCase):
    def test_skill_documents_switch_prompt_and_personality_actions_without_special_identity(self):
        root = Path(__file__).resolve().parents[1]
        skill = (root / "skills" / "clawchat-pet" / "SKILL.md").read_text(encoding="utf-8")
        references = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (root / "skills" / "clawchat-pet" / "references").glob("*.md")
        )

        self.assertNotIn("银月", skill + references)
        self.assertIn("prompt_personality", skill)
        self.assertIn("/api/v1/pets/current", skill)
        self.assertIn("/api/v1/pets/{slug}/personality", skill)
        for action in ("configure", "neutral", "reset"):
            self.assertIn(action, skill)
        self.assertIn("yinyue-2", skill)


if __name__ == "__main__":
    unittest.main()
