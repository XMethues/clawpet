import tempfile
import unittest
from pathlib import Path

from clawchat_pet.runtime import ClawchatPetRuntime
from tests.test_runtime_v2 import PETS


class GameplaySceneTests(unittest.TestCase):
    @staticmethod
    def event(event_id: str) -> dict:
        return {
            "event_id": event_id,
            "occurred_at": 100.0,
            "tool_call_id": event_id,
            "function_name": "read_file",
            "result": {"ok": True},
        }

    @staticmethod
    def values(presentation: dict) -> dict[str, float]:
        return {
            item["id"]: float(item["value"])
            for item in presentation["meters"] + presentation["attributes"]
        }

    def test_scene_switch_reprojects_the_same_settled_growth(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ClawchatPetRuntime(Path(tmp), pet_catalog=PETS)
            runtime.handle_activity("post_tool_call", self.event("success"))
            xianxia = runtime.presentation()

            star = runtime.command({
                "type": "select_scene", "scene_id": "star-voyage"
            })

        self.assertEqual(self.values(xianxia), self.values(star))
        self.assertEqual(xianxia["stage"]["index"], star["stage"]["index"])
        self.assertEqual("灵气", xianxia["meters"][0]["label"])
        self.assertEqual("航程数据", star["meters"][0]["label"])

    def test_duplicate_growth_event_stays_duplicate_after_scene_switch(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ClawchatPetRuntime(Path(tmp), pet_catalog=PETS)
            event = self.event("durable-success")

            self.assertEqual(
                "accepted", runtime.handle_activity("post_tool_call", event)
            )
            first = runtime.presentation()
            runtime.command({"type": "select_scene", "scene_id": "star-voyage"})
            runtime = ClawchatPetRuntime(Path(tmp), pet_catalog=PETS)
            self.assertEqual(
                "duplicate", runtime.handle_activity("post_tool_call", event)
            )
            second = runtime.presentation()

        self.assertEqual(self.values(first), self.values(second))
        self.assertEqual(
            1,
            sum(
                entry["kind"] == "work_succeeded"
                for entry in second["chronicle"]["entries"]
            ),
        )

    def test_star_scene_translates_facts_while_personality_changes_only_voice(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ClawchatPetRuntime(Path(tmp), pet_catalog=PETS)
            runtime.handle_activity("post_tool_call", self.event("success"))
            runtime.command({"type": "select_scene", "scene_id": "star-voyage"})
            runtime.command({"type": "select_pet", "pet_id": "boba"})
            presentation = runtime.command({
                "type": "configure_personality",
                "pet_id": "boba",
                "profile": {
                    "style": "brief mission control",
                    "lines": {"wave": ["Mission complete."]},
                },
            })

        self.assertEqual("Mission complete.", presentation["voice"]["text"])
        newest = presentation["chronicle"]["entries"][-1]["text"]
        self.assertIn("星图解码", newest)
        self.assertIn("航程数据 +2.4", newest)
        self.assertNotIn("灵气", newest)


if __name__ == "__main__":
    unittest.main()
