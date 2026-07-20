import json
import tempfile
import unittest
from pathlib import Path

from clawchat_pet.runtime import ClawchatPetRuntime
from tests.test_runtime_v2 import PETS


class GameplaySceneTests(unittest.TestCase):
    @staticmethod
    def event(event_id: str) -> dict:
        return {
            "schema_version": 1,
            "event_id": event_id,
            "occurred_at": 100.0,
            "kind": "tool_completed",
            "payload": {
                "activity_id": event_id,
                "tool_name": "read_file",
                "outcome": "success",
            },
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
            runtime.handle_activity(self.event("success"))
            xianxia = runtime.presentation()
            growth_before = json.loads(runtime.save_file.read_text())["cultivation"]

            star = runtime.command({
                "type": "select_scene", "scene_id": "star-voyage"
            })
            growth_after = json.loads(runtime.save_file.read_text())["cultivation"]

        self.assertEqual(growth_before, growth_after)
        self.assertEqual(self.values(xianxia), self.values(star))
        self.assertEqual(xianxia["stage"]["index"], star["stage"]["index"])
        self.assertEqual("灵气", xianxia["meters"][0]["label"])
        self.assertEqual("航程数据", star["meters"][0]["label"])

    def test_duplicate_growth_event_stays_duplicate_after_scene_switch(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ClawchatPetRuntime(Path(tmp), pet_catalog=PETS)
            event = self.event("durable-success")

            self.assertEqual("accepted", runtime.handle_activity(event))
            runtime.command({"type": "select_scene", "scene_id": "star-voyage"})
            self.assertEqual("duplicate", runtime.handle_activity(event))
            save = json.loads(runtime.save_file.read_text())

        self.assertEqual(1, save["cultivation"]["counters"]["tool_success_total"])

    def test_star_scene_translates_facts_while_personality_changes_only_voice(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ClawchatPetRuntime(Path(tmp), pet_catalog=PETS)
            runtime.handle_activity(self.event("success"))
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
