import tempfile
import unittest
import urllib.error
from pathlib import Path

from clawchat_pet.activity import ActivityRuntime
from clawchat_pet.server import ServerRunner
from tests.test_activity_runtime import get_json, post_json
from tests.test_pet_identity import PETS


class PersonalityHTTPTests(unittest.TestCase):
    def test_personality_is_per_pet_prompted_once_and_changes_only_utterances(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ActivityRuntime(Path(tmp) / "cultivation.json", pet_catalog=PETS)
            runner = ServerRunner(activity_runtime=runtime, bootstrap=lambda: None)
            runner.start(host="127.0.0.1", port=0)
            try:
                before = get_json(runner.base_url + "/cultivation")["stats"]
                _, selected = post_json(runner.base_url + "/api/v1/pets/current", {"slug": "boba"})
                _, configured = post_json(
                    runner.base_url + "/api/v1/pets/boba/personality",
                    {"action": "configure", "profile": {
                        "style": "brief and curious",
                        "lines": {"idle": ["Ready when you are."]},
                    }},
                )
                personality = get_json(runner.base_url + "/api/v1/pets/boba/personality")
                voice = get_json(runner.base_url + "/voice")
                _, away = post_json(runner.base_url + "/api/v1/pets/current", {"slug": "yinyue-2"})
                _, returned = post_json(runner.base_url + "/api/v1/pets/current", {"slug": "boba"})
                after = get_json(runner.base_url + "/cultivation")["stats"]
                _, neutral = post_json(
                    runner.base_url + "/api/v1/pets/boba/personality",
                    {"action": "neutral"},
                )
            finally:
                runner.stop()

        self.assertEqual("undecided", selected["personality_state"])
        self.assertTrue(selected["prompt_personality"])
        self.assertEqual("configured", configured["personality"]["state"])
        self.assertEqual("configured", personality["personality"]["state"])
        self.assertEqual({"speaker": "Boba", "text": "Ready when you are."}, {
            "speaker": voice["speaker"], "text": voice["text"],
        })
        self.assertTrue(away["prompt_personality"])
        self.assertFalse(returned["prompt_personality"])
        self.assertEqual(before, after)
        self.assertEqual("neutral", neutral["personality"]["state"])

    def test_decline_suppresses_future_prompt_until_explicit_reset(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ActivityRuntime(Path(tmp) / "cultivation.json", pet_catalog=PETS)
            runner = ServerRunner(activity_runtime=runtime, bootstrap=lambda: None)
            runner.start(host="127.0.0.1", port=0)
            try:
                _, declined = post_json(
                    runner.base_url + "/api/v1/pets/boba/personality",
                    {"action": "decline"},
                )
                _, selected = post_json(
                    runner.base_url + "/api/v1/pets/current", {"slug": "boba"}
                )
                _, reset = post_json(
                    runner.base_url + "/api/v1/pets/boba/personality",
                    {"action": "reset"},
                )
                _, selected_after_reset = post_json(
                    runner.base_url + "/api/v1/pets/current", {"slug": "boba"}
                )
            finally:
                runner.stop()

        self.assertEqual("neutral", declined["personality"]["state"])
        self.assertFalse(selected["prompt_personality"])
        self.assertEqual("undecided", reset["personality"]["state"])
        self.assertTrue(selected_after_reset["prompt_personality"])

    def test_profile_can_be_replaced_and_invalid_schema_preserves_last_valid_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ActivityRuntime(Path(tmp) / "cultivation.json", pet_catalog=PETS)
            runner = ServerRunner(activity_runtime=runtime, bootstrap=lambda: None)
            runner.start(host="127.0.0.1", port=0)
            try:
                post_json(runner.base_url + "/api/v1/pets/current", {"slug": "boba"})
                post_json(
                    runner.base_url + "/api/v1/pets/boba/personality",
                    {"action": "configure", "profile": {
                        "style": "first", "lines": {"idle": ["First line."]},
                    }},
                )
                _, replaced = post_json(
                    runner.base_url + "/api/v1/pets/boba/personality",
                    {"action": "configure", "profile": {
                        "style": "second", "lines": {
                            "idle": ["Second line."], "failed": ["Try again."],
                        },
                    }},
                )
                voice = get_json(runner.base_url + "/voice")
                invalid_profiles = [
                    {"style": "x", "lines": {"idle": ["ok"]}, "extra": True},
                    {"style": "", "lines": {"idle": ["ok"]}},
                    {"style": "x", "lines": {"unsupported": ["ok"]}},
                    {"style": "x", "lines": {"idle": []}},
                    {"style": "x", "lines": {"idle": ["x" * 201]}},
                ]
                for profile in invalid_profiles:
                    with self.assertRaises(urllib.error.HTTPError) as rejected:
                        post_json(
                            runner.base_url + "/api/v1/pets/boba/personality",
                            {"action": "configure", "profile": profile},
                        )
                    self.assertEqual(400, rejected.exception.code)
                stored = get_json(
                    runner.base_url + "/api/v1/pets/boba/personality"
                )["personality"]
            finally:
                runner.stop()

        self.assertEqual("second", replaced["personality"]["profile"]["style"])
        self.assertEqual("Second line.", voice["text"])
        self.assertEqual(replaced["personality"], stored)


if __name__ == "__main__":
    unittest.main()
