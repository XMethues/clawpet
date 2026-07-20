import json
import tempfile
import unittest
from pathlib import Path

from clawchat_pet.runtime import ClawchatPetRuntime


PETS = [
    {
        "slug": "yinyue-2",
        "displayName": "Yinyue",
        "source": "petdex",
        "assetKind": "sprite",
        "cached": True,
        "spriteUrl": "/assets/pets/yinyue-2.png",
        "cellWidth": 192,
        "cellHeight": 208,
    },
    {
        "slug": "boba",
        "displayName": "Boba",
        "source": "petdex",
        "assetKind": "sprite",
        "cached": True,
        "spriteUrl": "/assets/pets/boba.png",
        "cellWidth": 192,
        "cellHeight": 208,
    },
]


class RuntimeInterfaceTests(unittest.TestCase):
    def test_new_runtime_owns_one_save_and_ignores_legacy_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp)
            (runtime_dir / "cultivation.json").write_text(
                json.dumps({"stats": {"qi": 999}}), encoding="utf-8"
            )

            runtime = ClawchatPetRuntime(
                runtime_dir,
                pet_catalog=PETS,
                clock=lambda: 1_000.0,
            )

            presentation = runtime.presentation()
            catalog = runtime.catalog()

            self.assertEqual("xianxia", presentation["scene"]["id"])
            self.assertEqual("qingming", presentation["skin"]["id"])
            self.assertEqual("yinyue-2", presentation["pet"]["slug"])
            self.assertEqual(0, presentation["stage"]["index"])
            self.assertEqual("xianxia", catalog["active"]["scene_id"])
            self.assertEqual("qingming", catalog["active"]["skin_id"])
            self.assertTrue((runtime_dir / "save.json").is_file())
            self.assertEqual(999, json.loads(
                (runtime_dir / "cultivation.json").read_text(encoding="utf-8")
            )["stats"]["qi"])

    def test_scene_and_skin_commands_preserve_one_coherent_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp)
            runtime = ClawchatPetRuntime(
                runtime_dir,
                pet_catalog=PETS,
                clock=lambda: 1_000.0,
            )

            selected = runtime.command({"type": "select_skin", "skin_id": "chiyan"})
            customized = runtime.command({
                "type": "customize_skin",
                "skin_id": "chiyan",
                "visual": {"accent": "#123456"},
            })
            voyage = runtime.command({
                "type": "select_scene", "scene_id": "star-voyage"
            })

            self.assertEqual("chiyan", selected["skin"]["id"])
            self.assertEqual("#123456", customized["skin"]["visual"]["accent"])
            self.assertEqual("star-voyage", voyage["scene"]["id"])
            self.assertEqual("xinghai", voyage["skin"]["id"])
            self.assertEqual("star-voyage", voyage["skin"]["scene_id"])

            with self.assertRaisesRegex(ValueError, "does not belong"):
                runtime.command({"type": "select_skin", "skin_id": "qingming"})

            restarted = ClawchatPetRuntime(
                runtime_dir,
                pet_catalog=PETS,
                clock=lambda: 1_000.0,
            )
            persisted = json.loads(
                (runtime_dir / "save.json").read_text(encoding="utf-8")
            )
            catalog = restarted.catalog()

            self.assertEqual("star-voyage", catalog["active"]["scene_id"])
            self.assertEqual("xinghai", catalog["active"]["skin_id"])
            self.assertEqual(
                {"chiyan": {"accent": "#123456"}},
                persisted["presentation"]["skin_overrides"],
            )
            self.assertEqual(
                "qingming",
                next(scene for scene in catalog["scenes"] if scene["id"] == "xianxia")[
                    "default_skin_id"
                ],
            )

    def test_reset_skin_removes_only_the_users_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ClawchatPetRuntime(Path(tmp), pet_catalog=PETS)
            runtime.command({
                "type": "customize_skin",
                "skin_id": "qingming",
                "visual": {"accent": "magenta"},
            })

            reset = runtime.command({"type": "reset_skin", "skin_id": "qingming"})

            self.assertEqual("#65c8ff", reset["skin"]["visual"]["accent"])
            self.assertEqual({}, json.loads(runtime.save_file.read_text())["presentation"]["skin_overrides"])

    def test_pet_personality_and_strategy_commands_share_the_same_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp)
            runtime = ClawchatPetRuntime(runtime_dir, pet_catalog=PETS)

            selected = runtime.command({"type": "select_pet", "pet_id": "boba"})
            configured = runtime.command({
                "type": "configure_personality",
                "pet_id": "boba",
                "profile": {
                    "style": "brief",
                    "lines": {"idle": ["Ready."]},
                },
            })
            strategic = runtime.command({
                "type": "select_strategy", "strategy_id": "advance"
            })

            self.assertEqual("boba", selected["pet"]["slug"])
            self.assertTrue(selected["pet"]["prompt_personality"])
            self.assertEqual("Ready.", configured["voice"]["text"])
            self.assertEqual("advance", strategic["strategy"]["id"])
            self.assertEqual(0, strategic["stage"]["index"])

            restarted = ClawchatPetRuntime(runtime_dir, pet_catalog=PETS)
            presentation = restarted.presentation()
            persisted = json.loads(runtime.save_file.read_text())

            self.assertEqual("boba", presentation["pet"]["slug"])
            self.assertEqual("configured", presentation["pet"]["personality_state"])
            self.assertEqual("冲关", persisted["cultivation"]["policy"]["name"])
            self.assertFalse((runtime_dir / "current_pet.json").exists())
            self.assertFalse((runtime_dir / "personalities.json").exists())

    def test_personality_commands_are_explicit_and_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ClawchatPetRuntime(Path(tmp), pet_catalog=PETS)

            with self.assertRaisesRegex(ValueError, "unsupported event groups"):
                runtime.command({
                    "type": "configure_personality",
                    "pet_id": "yinyue-2",
                    "profile": {"style": "x", "lines": {"invalid": ["no"]}},
                })

            neutral = runtime.command({
                "type": "set_neutral_personality", "pet_id": "yinyue-2"
            })
            reset = runtime.command({
                "type": "reset_personality", "pet_id": "yinyue-2"
            })

            self.assertEqual("neutral", neutral["pet"]["personality_state"])
            self.assertEqual("undecided", reset["pet"]["personality_state"])

    def test_time_based_dormancy_is_settled_lazily_without_a_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = [1_000.0]
            runtime = ClawchatPetRuntime(
                Path(tmp), pet_catalog=PETS, clock=lambda: now[0]
            )
            now[0] += 2 * 86_400

            runtime.presentation()
            first = json.loads(runtime.save_file.read_text())
            runtime.presentation()
            second = json.loads(runtime.save_file.read_text())

            self.assertEqual(2, first["cultivation"]["dormancy"]["last_applied_stage"])
            self.assertEqual(
                first["cultivation"]["stats"], second["cultivation"]["stats"]
            )

    def test_activity_and_lazy_aging_use_the_same_injected_clock(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = [1_000.0]
            runtime = ClawchatPetRuntime(
                Path(tmp), pet_catalog=PETS, clock=lambda: now[0]
            )
            runtime.handle_activity({
                "schema_version": 1,
                "event_id": "start",
                "occurred_at": now[0],
                "kind": "tool_started",
                "payload": {"activity_id": "tool", "tool_name": "read_file"},
            })
            now[0] += 2 * 86_400

            runtime.presentation()
            save = json.loads(runtime.save_file.read_text())

            self.assertEqual(1_000.0, save["cultivation"]["profile"]["last_active"])
            self.assertEqual(2, save["cultivation"]["dormancy"]["last_applied_stage"])

    def test_expired_activity_does_not_keep_the_last_tool_capability(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = [1_000.0]
            runtime = ClawchatPetRuntime(
                Path(tmp), pet_catalog=PETS, clock=lambda: now[0]
            )
            runtime.handle_activity({
                "schema_version": 1,
                "event_id": "finish",
                "occurred_at": now[0],
                "kind": "tool_completed",
                "payload": {
                    "activity_id": "tool",
                    "tool_name": "read_file",
                    "outcome": "success",
                },
            })
            active = runtime.presentation()
            now[0] += 4
            expired = runtime.presentation()

            self.assertEqual("file-inspection", active["activity"]["capability"]["id"])
            self.assertEqual("idle", expired["activity"]["state"])
            self.assertIsNone(expired["activity"]["capability"])


if __name__ == "__main__":
    unittest.main()
