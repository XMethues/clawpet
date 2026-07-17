import json
import tempfile
import unittest
from pathlib import Path

from clawchat_pet.activity import ActivityRuntime
from clawchat_pet.server import ServerRunner
from clawchat_pet.simulator import default_save
from tests.test_activity_runtime import get_json, post_json


PETS = [
    {"slug": "yinyue-2", "displayName": "Yinyue", "source": "petdex", "assetKind": "sprite", "cached": True, "cellWidth": 192, "cellHeight": 208},
    {"slug": "boba", "displayName": "Boba", "source": "petdex", "assetKind": "sprite", "cached": True, "cellWidth": 192, "cellHeight": 208},
]


class FakePet:
    def __init__(self, data):
        self.slug = data["slug"]
        self.data = data

    def to_dict(self):
        return dict(self.data)


class FakePetdex:
    def __init__(self):
        self.selected = []
        self.uncached = FakePet({
            "slug": "boba", "displayName": "Boba", "source": "petdex",
            "cached": False, "spriteUrl": None,
        })
        self.cached = FakePet({
            "slug": "boba", "displayName": "Boba", "source": "petdex",
            "cached": True, "spriteUrl": "/api/v1/pets/boba/sprite.png",
        })

    def list_pets(self, force=False):
        return [self.uncached]

    def set_current_pet(self, slug):
        self.selected.append(slug)
        return self.cached


class PetIdentityHTTPTests(unittest.TestCase):
    def test_legacy_save_progress_is_preserved_during_runtime_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            hermes_home = Path(tmp)
            legacy = hermes_home / "cultivation" / "yinyue.json"
            legacy.parent.mkdir(parents=True)
            save = default_save()
            save["stats"]["qi"] = 17.0
            legacy.write_text(json.dumps(save), encoding="utf-8")

            runtime = ActivityRuntime(
                hermes_home / "clawchat-pet" / "cultivation.json",
                pet_catalog=PETS,
            )
            cultivation = runtime.cultivation_state()

        self.assertEqual(17.0, cultivation["stats"]["qi"])

    def test_current_pet_is_authoritative_while_cultivation_progress_is_shared(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ActivityRuntime(Path(tmp) / "cultivation.json", pet_catalog=PETS)
            runner = ServerRunner(activity_runtime=runtime, bootstrap=lambda: None)
            runner.start(host="127.0.0.1", port=0)
            try:
                default_pet = get_json(runner.base_url + "/api/v1/pets/current")["pet"]
                post_json(runner.base_url + "/api/v1/events", {
                    "schema_version": 1, "event_id": "success-1", "occurred_at": 1,
                    "kind": "tool_completed",
                    "payload": {"activity_id": "tool", "tool_name": "read_file", "outcome": "success"},
                })
                before = get_json(runner.base_url + "/cultivation")
                _, switched = post_json(runner.base_url + "/api/v1/pets/current", {"slug": "boba"})
                after = get_json(runner.base_url + "/cultivation")
                voice = get_json(runner.base_url + "/voice")
            finally:
                runner.stop()

        self.assertEqual("yinyue-2", default_pet["slug"])
        self.assertEqual("boba", switched["pet"]["slug"])
        self.assertEqual(before["stats"], after["stats"])
        self.assertEqual("Boba", after["profile"]["name"])
        self.assertEqual("Boba", voice["speaker"])
        self.assertNotIn("银月", str(after))

    def test_production_selection_caches_petdex_sprite_before_returning_it(self):
        provider = FakePetdex()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ActivityRuntime(
                Path(tmp) / "cultivation.json", pet_provider=provider
            )
            runner = ServerRunner(activity_runtime=runtime, bootstrap=lambda: None)
            runner.start(host="127.0.0.1", port=0)
            try:
                _, selected = post_json(
                    runner.base_url + "/api/v1/pets/current", {"slug": "boba"}
                )
            finally:
                runner.stop()

        self.assertEqual(["boba"], provider.selected)
        self.assertTrue(selected["pet"]["cached"])
        self.assertEqual(
            "/api/v1/pets/boba/sprite.png", selected["pet"]["spriteUrl"]
        )


if __name__ == "__main__":
    unittest.main()
