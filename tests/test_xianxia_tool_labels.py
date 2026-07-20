import tempfile
import unittest
from pathlib import Path

from clawchat_pet.runtime import ClawchatPetRuntime
from tests.test_runtime_v2 import PETS


class XianxiaToolLabelTests(unittest.TestCase):
    @staticmethod
    def completed(tool: str, outcome: str) -> dict:
        return {
            "event_id": f"{tool}-{outcome}",
            "occurred_at": 10.0,
            "tool_call_id": tool,
            "function_name": tool,
            "result": (
                {"ok": True}
                if outcome == "success"
                else {"ok": False, "error": "failed"}
            ),
        }

    def test_success_log_uses_xianxia_name_instead_of_raw_tool_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ClawchatPetRuntime(Path(tmp), pet_catalog=PETS)
            runtime.handle_activity(
                "post_tool_call", self.completed("read_file", "success")
            )

            text = runtime.presentation()["chronicle"]["entries"][-1]["text"]
        self.assertIn("天机推演", text)
        self.assertNotIn("read_file", text)

    def test_failure_log_hides_unknown_raw_tool_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ClawchatPetRuntime(Path(tmp), pet_catalog=PETS)
            runtime.handle_activity(
                "post_tool_call", self.completed("future_tool", "failure")
            )

            text = runtime.presentation()["chronicle"]["entries"][-1]["text"]
        self.assertIn("无名术法", text)
        self.assertNotIn("future_tool", text)

if __name__ == "__main__":
    unittest.main()
