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
    def test_gateway_asset_warm_uses_the_current_saved_pet(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            yinyue_sprite = directory / "yinyue.webp"
            boba_sprite = directory / "boba.webp"
            yinyue_sprite.write_bytes(b"yinyue")
            boba_sprite.write_bytes(b"boba")
            pets = [
                {**PETS[0], "spritePath": str(yinyue_sprite)},
                {**PETS[1], "spritePath": str(boba_sprite)},
            ]
            runtime = ClawchatPetRuntime(directory, pet_catalog=pets)
            runtime.command({"type": "select_pet", "pet_id": "boba"})

            warmed = runtime.ensure_current_pet_asset()

        self.assertEqual(boba_sprite, warmed)

    def test_new_runtime_owns_one_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp)

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

    def test_runtime_refuses_a_noncurrent_save_instead_of_converting_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            save_file = Path(tmp) / "save.json"
            save_file.write_text(
                json.dumps({"version": 1, "cultivation": {}}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "delete .*save.json"):
                ClawchatPetRuntime(Path(tmp), pet_catalog=PETS)

    def test_runtime_refuses_a_damaged_current_save_at_startup(self):
        with tempfile.TemporaryDirectory() as tmp:
            save_file = Path(tmp) / "save.json"
            save_file.write_text(
                json.dumps({
                    "version": 2,
                    "growth": {},
                    "pet": {"current": "yinyue-2", "personalities": {}},
                    "presentation": {},
                }),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "delete .*save.json"):
                ClawchatPetRuntime(Path(tmp), pet_catalog=PETS)

    def test_raw_tools_are_aggregated_into_stable_capabilities(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ClawchatPetRuntime(Path(tmp), pet_catalog=PETS)
            for tool in ("read_file", "search_files"):
                runtime.handle_activity("pre_tool_call", {
                    "event_id": f"{tool}-start",
                    "occurred_at": 1_000.0,
                    "tool_call_id": tool,
                    "tool_name": tool,
                })
                runtime.handle_activity("post_tool_call", {
                    "event_id": f"{tool}-done",
                    "occurred_at": 1_001.0,
                    "tool_call_id": tool,
                    "function_name": tool,
                    "result": {"ok": True},
                })

            presentation = runtime.presentation()

        self.assertEqual(
            ["file-inspection"],
            [item["id"] for item in presentation["capabilities"]],
        )
        self.assertEqual(
            ["asset:file-inspection"],
            [item["id"] for item in presentation["assets"]],
        )

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
                "visual": {
                    "accent": "#123456",
                    "backgroundImage": "url('https://example.com/custom.webp')",
                },
            })
            voyage = runtime.command({
                "type": "select_scene", "scene_id": "star-voyage"
            })

            self.assertEqual("chiyan", selected["skin"]["id"])
            self.assertEqual("#123456", customized["skin"]["visual"]["accent"])
            self.assertEqual(
                "url('https://example.com/custom.webp')",
                customized["skin"]["visual"]["backgroundImage"],
            )
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
                {
                    "chiyan": {
                        "accent": "#123456",
                        "backgroundImage": "url('https://example.com/custom.webp')",
                    }
                },
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

            self.assertEqual("boba", presentation["pet"]["slug"])
            self.assertEqual("configured", presentation["pet"]["personality_state"])
            self.assertEqual("advance", presentation["strategy"]["id"])
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

            first = runtime.presentation()
            second = runtime.presentation()

            first_values = {
                item["id"]: item["value"]
                for item in first["meters"] + first["attributes"]
            }
            self.assertEqual(0.75, first_values["risk"])
            self.assertEqual(0.93, first_values["stability"])
            self.assertEqual(first, second)

    def test_activity_and_lazy_aging_use_the_same_injected_clock(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = [1_000.0]
            runtime = ClawchatPetRuntime(
                Path(tmp), pet_catalog=PETS, clock=lambda: now[0]
            )
            runtime.handle_activity("pre_tool_call", {
                "event_id": "start",
                "occurred_at": now[0],
                "tool_call_id": "tool",
                "tool_name": "read_file",
            })
            now[0] += 2 * 86_400

            presentation = runtime.presentation()
            values = {
                item["id"]: item["value"]
                for item in presentation["meters"] + presentation["attributes"]
            }

            self.assertEqual(0.75, values["risk"])
            self.assertEqual(
                ["idle_decay", "idle_decay"],
                [
                    entry["kind"]
                    for entry in presentation["chronicle"]["entries"][-2:]
                ],
            )

    def test_expired_activity_does_not_keep_the_last_tool_capability(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = [1_000.0]
            runtime = ClawchatPetRuntime(
                Path(tmp), pet_catalog=PETS, clock=lambda: now[0]
            )
            runtime.handle_activity("post_tool_call", {
                "event_id": "finish",
                "occurred_at": now[0],
                "tool_call_id": "tool",
                "function_name": "read_file",
                "result": {"ok": True},
            })
            active = runtime.presentation()
            now[0] += 4
            expired = runtime.presentation()

            self.assertEqual("file-inspection", active["activity"]["capability"]["id"])
            self.assertEqual("idle", expired["activity"]["state"])
            self.assertIsNone(expired["activity"]["capability"])


if __name__ == "__main__":
    unittest.main()
