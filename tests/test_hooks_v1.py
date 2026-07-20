import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clawchat_pet.hooks import register_hooks
from clawchat_pet.runtime import ClawchatPetRuntime
from tests.test_runtime_v2 import PETS


class HookContext:
    def __init__(self):
        self.callbacks = {}

    def register_hook(self, name, callback):
        self.callbacks[name] = callback


class RecordingRuntime:
    def __init__(self):
        self.calls = []

    def handle_activity(self, callback_name, raw_kwargs):
        self.calls.append((callback_name, raw_kwargs))


class DirectHookTests(unittest.TestCase):
    def runtime_and_hooks(self, directory: str):
        runtime = ClawchatPetRuntime(Path(directory), pet_catalog=PETS)
        context = HookContext()
        register_hooks(context, runtime)
        return runtime, context.callbacks

    def test_hook_adapter_forwards_raw_callback_without_interpreting_it(self):
        runtime = RecordingRuntime()
        context = HookContext()
        register_hooks(context, runtime)
        result = {"ok": True}

        context.callbacks["post_tool_call"](
            function_name="read_file",
            tool_call_id="call-1",
            result=result,
        )

        self.assertEqual(1, len(runtime.calls))
        callback_name, raw_kwargs = runtime.calls[0]
        self.assertEqual("post_tool_call", callback_name)
        self.assertIs(result, raw_kwargs["result"])

    def test_hooks_call_the_runtime_directly_without_an_http_event_adapter(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime, hooks = self.runtime_and_hooks(tmp)

            hooks["pre_tool_call"](tool_name="read_file", tool_call_id="call-1")
            running = runtime.presentation()
            hooks["post_tool_call"](
                function_name="read_file",
                tool_call_id="call-1",
                result={"ok": True},
            )
            completed = runtime.presentation()

            self.assertEqual("run", running["activity"]["state"])
            self.assertEqual("wave", completed["activity"]["state"])
            self.assertEqual(2.4, completed["meters"][0]["value"])
            self.assertEqual(
                1,
                sum(
                    entry["kind"] == "work_succeeded"
                    for entry in completed["chronicle"]["entries"]
                ),
            )

    def test_parallel_idless_lifecycles_remain_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime, hooks = self.runtime_and_hooks(tmp)

            hooks["pre_tool_call"](tool_name="read_file")
            hooks["pre_tool_call"](tool_name="read_file")
            both = runtime.activity_state()
            hooks["post_tool_call"](function_name="read_file", result={"ok": True})
            one = runtime.activity_state()

            self.assertEqual(2, both["in_flight"]["tools"])
            self.assertEqual(1, one["in_flight"]["tools"])

    def test_smart_approval_is_inference_and_human_approval_is_waiting(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime, hooks = self.runtime_and_hooks(tmp)

            hooks["pre_approval_request"](approval_id="smart", surface="smart")
            smart = runtime.activity_state()
            hooks["post_approval_response"](approval_id="smart", choice="once")
            hooks["pre_approval_request"](approval_id="human", surface="cli")
            human = runtime.activity_state()

            self.assertEqual("review", smart["state"])
            self.assertEqual("waiting", human["state"])

    def test_rejected_approval_neutralizes_the_tool_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime, hooks = self.runtime_and_hooks(tmp)
            hooks["pre_tool_call"](tool_name="terminal", tool_call_id="blocked")
            hooks["pre_approval_request"](
                approval_id="approval", surface="cli", tool_call_id="blocked"
            )
            hooks["post_approval_response"](
                approval_id="approval", choice="deny", tool_call_id="blocked"
            )
            hooks["post_tool_call"](
                function_name="terminal",
                tool_call_id="blocked",
                result={"ok": False, "error": "permission denied"},
            )

            presentation = runtime.presentation()

            self.assertEqual("unknown", runtime.activity_state()["state"])
            self.assertEqual(0.0, presentation["meters"][1]["value"])
            self.assertFalse(any(
                entry["kind"] == "work_failed"
                for entry in presentation["chronicle"]["entries"]
            ))

    def test_activity_priority_combines_turn_subagent_tool_and_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime, hooks = self.runtime_and_hooks(tmp)

            hooks["pre_llm_call"](session_id="turn")
            self.assertEqual("review", runtime.activity_state()["state"])
            hooks["subagent_start"](subagent_id="sub")
            self.assertEqual("subagent", runtime.activity_state()["state"])
            hooks["pre_tool_call"](tool_name="delegate_task", tool_call_id="tool")
            self.assertEqual("run", runtime.activity_state()["state"])
            hooks["pre_approval_request"](
                approval_id="approval", surface="cli", tool_call_id="tool"
            )
            self.assertEqual("waiting", runtime.activity_state()["state"])
            hooks["post_approval_response"](
                approval_id="approval", choice="once", tool_call_id="tool"
            )
            self.assertEqual("run", runtime.activity_state()["state"])
            hooks["post_tool_call"](
                function_name="delegate_task",
                tool_call_id="tool",
                result={"ok": True},
            )
            self.assertEqual("subagent", runtime.activity_state()["state"])
            hooks["subagent_stop"](subagent_id="sub")
            self.assertEqual("wave", runtime.activity_state()["state"])

    def test_failed_save_commits_neither_growth_nor_transient_activity(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime, hooks = self.runtime_and_hooks(tmp)
            hooks["pre_tool_call"](tool_name="read_file", tool_call_id="tool")
            completion = {
                "event_id": "completion",
                "occurred_at": 2.0,
                "tool_call_id": "tool",
                "function_name": "read_file",
                "result": {"ok": True},
            }

            with patch.object(runtime, "_write", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    runtime.handle_activity("post_tool_call", completion)

            presentation = runtime.presentation()
            self.assertEqual("run", runtime.activity_state()["state"])
            self.assertEqual(0.0, presentation["meters"][0]["value"])
            self.assertFalse(any(
                entry["kind"] == "work_succeeded"
                for entry in presentation["chronicle"]["entries"]
            ))

            hooks["pre_approval_request"](
                approval_id="approval", surface="cli"
            )
            hooks["post_approval_response"](
                approval_id="approval", choice="deny"
            )
            hooks["post_tool_call"](
                function_name="read_file",
                tool_call_id="tool",
                result={"ok": False, "error": "denied"},
            )
            self.assertEqual(0.0, runtime.presentation()["meters"][1]["value"])

    def test_transient_activity_resets_to_idle_on_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, hooks = self.runtime_and_hooks(tmp)
            hooks["pre_tool_call"](tool_name="read_file", tool_call_id="running")

            restarted = ClawchatPetRuntime(Path(tmp), pet_catalog=PETS)

            self.assertEqual("run", first.activity_state()["state"])
            self.assertEqual("idle", restarted.activity_state()["state"])
            self.assertIsNone(restarted.presentation()["activity"]["capability"])


if __name__ == "__main__":
    unittest.main()
