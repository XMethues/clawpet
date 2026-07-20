import json
import tempfile
import unittest
import urllib.error
from dataclasses import replace
from pathlib import Path

from clawchat_pet.activity import ActivityRuntime
from clawchat_pet.gameplay import GameplayScenes, STAR_VOYAGE_SCENE, XIANXIA_SCENE
from clawchat_pet.server import ServerRunner
from tests.test_activity_runtime import get_json, post_json
from tests.test_pet_identity import PETS


class GameplaySceneTests(unittest.TestCase):
    @staticmethod
    def event(event_id: str, outcome: str = "success") -> dict:
        return {
            "schema_version": 1,
            "event_id": event_id,
            "occurred_at": 100.0,
            "kind": "tool_completed",
            "payload": {
                "activity_id": event_id,
                "tool_name": "read_file",
                "outcome": outcome,
            },
        }

    @staticmethod
    def meter_values(experience: dict) -> dict[str, float]:
        return {
            str(item["id"]): float(item["value"])
            for item in experience["meters"] + experience["attributes"]
        }

    def test_xianxia_is_default_and_two_real_scene_adapters_are_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ActivityRuntime(Path(tmp) / "cultivation.json", pet_catalog=PETS)

            catalog = runtime.list_gameplay_scenes()
            experience = runtime.experience_state()

        self.assertEqual("xianxia", catalog["current_scene"])
        self.assertEqual(["xianxia", "star-voyage"], [
            scene["id"] for scene in catalog["scenes"]
        ])
        self.assertEqual("xianxia", experience["scene"]["id"])
        self.assertEqual("炼气1层", experience["stage"]["label"])
        self.assertEqual("灵气", experience["meters"][0]["label"])

    def test_third_scene_is_added_by_definition_without_changing_the_projector(self):
        ocean_scene = replace(
            STAR_VOYAGE_SCENE,
            id="ocean-voyage",
            name="远洋航行",
            stage_labels=tuple(
                f"海域 {index + 1}" for index in range(len(STAR_VOYAGE_SCENE.stage_labels))
            ),
            stage_badges=tuple("航海" for _ in STAR_VOYAGE_SCENE.stage_badges),
            end_label="更远海域待开放",
            meter_labels={
                **STAR_VOYAGE_SCENE.meter_labels,
                "primary": "航海里程",
                "risk": "船体风险",
            },
        )
        scenes = GameplayScenes((XIANXIA_SCENE, STAR_VOYAGE_SCENE, ocean_scene))

        with tempfile.TemporaryDirectory() as tmp:
            runtime = ActivityRuntime(
                Path(tmp) / "cultivation.json",
                pet_catalog=PETS,
                gameplay_scenes=scenes,
            )
            runtime.select_gameplay_scene("ocean-voyage")
            experience = runtime.experience_state()

        self.assertEqual("远洋航行", experience["scene"]["name"])
        self.assertEqual("海域 1", experience["stage"]["label"])
        self.assertEqual("航海里程", experience["meters"][0]["label"])
        self.assertEqual("船体风险", experience["meters"][1]["label"])

    def test_scene_switch_reprojects_one_progress_without_mutating_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            save_file = Path(tmp) / "cultivation.json"
            runtime = ActivityRuntime(save_file, pet_catalog=PETS)
            runtime.ingest(self.event("success-1"))
            xianxia = runtime.experience_state()
            save_before = save_file.read_bytes()

            selected = runtime.select_gameplay_scene("star-voyage")
            star_voyage = runtime.experience_state()
            save_after = save_file.read_bytes()

            restarted = ActivityRuntime(save_file, pet_catalog=PETS)
            restarted_scene = restarted.current_gameplay_scene()

        self.assertEqual("star-voyage", selected["id"])
        self.assertEqual(save_before, save_after)
        self.assertEqual(self.meter_values(xianxia), self.meter_values(star_voyage))
        self.assertEqual(xianxia["stage"]["index"], star_voyage["stage"]["index"])
        self.assertEqual("航程数据", star_voyage["meters"][0]["label"])
        self.assertEqual("故障风险", star_voyage["meters"][1]["label"])
        self.assertEqual("star-voyage", restarted_scene["id"])

    def test_duplicate_event_remains_duplicate_across_scene_switch(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ActivityRuntime(Path(tmp) / "cultivation.json", pet_catalog=PETS)
            event = self.event("durable-success")

            self.assertEqual("accepted", runtime.ingest(event))
            runtime.select_gameplay_scene("star-voyage")
            self.assertEqual("duplicate", runtime.ingest(event))
            state = runtime.cultivation_state()

        self.assertEqual(1, state["counters"]["tool_success_total"])

    def test_unknown_scene_preserves_the_previous_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ActivityRuntime(Path(tmp) / "cultivation.json", pet_catalog=PETS)
            runtime.select_gameplay_scene("star-voyage")

            with self.assertRaises(KeyError):
                runtime.select_gameplay_scene("missing")

            current = runtime.current_gameplay_scene()

        self.assertEqual("star-voyage", current["id"])

    def test_star_voyage_renders_structured_facts_and_personality_only_changes_voice(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ActivityRuntime(Path(tmp) / "cultivation.json", pet_catalog=PETS)
            before = runtime.cultivation_state()["stats"]
            runtime.ingest(self.event("success-1"))
            runtime.select_gameplay_scene("star-voyage")
            runtime.select_pet("boba")
            runtime.update_personality("boba", {
                "action": "configure",
                "profile": {
                    "style": "brief mission control",
                    "lines": {"wave": ["Mission complete."]},
                },
            })

            experience = runtime.experience_state()
            after = runtime.cultivation_state()["stats"]

        self.assertEqual(before["qi"] + 2.4, after["qi"])
        self.assertEqual("Boba", experience["voice"]["speaker"])
        self.assertEqual("Mission complete.", experience["voice"]["text"])
        newest = experience["chronicle"]["entries"][-1]["text"]
        self.assertIn("星图解码", newest)
        self.assertIn("航程数据 +2.4", newest)
        self.assertNotIn("灵气", newest)
        self.assertNotIn("天机", newest)

    def test_http_scene_interface_and_experience_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ActivityRuntime(Path(tmp) / "cultivation.json", pet_catalog=PETS)
            runner = ServerRunner(activity_runtime=runtime, bootstrap=lambda: None)
            runner.start(host="127.0.0.1", port=0)
            try:
                catalog = get_json(runner.base_url + "/api/v1/scenes")
                _, selected = post_json(
                    runner.base_url + "/api/v1/scenes/current",
                    {"id": "star-voyage"},
                )
                current = get_json(runner.base_url + "/api/v1/scenes/current")
                experience = get_json(runner.base_url + "/api/v1/experience")
                with self.assertRaises(urllib.error.HTTPError) as missing:
                    post_json(
                        runner.base_url + "/api/v1/scenes/current",
                        {"id": "missing"},
                    )
            finally:
                runner.stop()

        self.assertEqual(2, catalog["count"])
        self.assertEqual("star-voyage", selected["scene"]["id"])
        self.assertEqual("star-voyage", current["scene"]["id"])
        self.assertEqual("star-voyage", experience["scene"]["id"])
        self.assertIn("skin", experience)
        self.assertEqual(404, missing.exception.code)


if __name__ == "__main__":
    unittest.main()
