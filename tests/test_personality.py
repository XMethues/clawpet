import json
import tempfile
import unittest
from pathlib import Path

from clawchat_pet.runtime import ClawchatPetRuntime
from tests.test_runtime_v2 import PETS


class PersonalityTests(unittest.TestCase):
    def test_personality_is_per_pet_and_does_not_change_growth(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ClawchatPetRuntime(Path(tmp), pet_catalog=PETS)
            before = json.loads(runtime.save_file.read_text())["cultivation"]
            runtime.command({"type": "select_pet", "pet_id": "boba"})
            configured = runtime.command({
                "type": "configure_personality",
                "pet_id": "boba",
                "profile": {"style": "brief", "lines": {"idle": ["Ready."]}},
            })
            runtime.command({"type": "select_pet", "pet_id": "yinyue-2"})
            returned = runtime.command({"type": "select_pet", "pet_id": "boba"})
            after = json.loads(runtime.save_file.read_text())["cultivation"]

        self.assertEqual("Ready.", configured["voice"]["text"])
        self.assertFalse(returned["pet"]["prompt_personality"])
        self.assertEqual(before, after)

    def test_invalid_replacement_preserves_the_last_valid_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ClawchatPetRuntime(Path(tmp), pet_catalog=PETS)
            command = {
                "type": "configure_personality",
                "pet_id": "boba",
                "profile": {"style": "valid", "lines": {"idle": ["First."]}},
            }
            runtime.command(command)

            with self.assertRaises(ValueError):
                runtime.command({
                    **command,
                    "profile": {"style": "", "lines": {"idle": []}},
                })

            runtime.command({"type": "select_pet", "pet_id": "boba"})
            self.assertEqual("First.", runtime.presentation()["voice"]["text"])


if __name__ == "__main__":
    unittest.main()
