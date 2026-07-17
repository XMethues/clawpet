import tempfile
import unittest
from pathlib import Path

from clawchat_pet.activity import ActivityRuntime
from clawchat_pet.hooks import register_hooks
from clawchat_pet.server import ServerRunner
from tests.test_activity_runtime import get_json


class HookContext:
    def __init__(self):
        self.callbacks = {}

    def register_hook(self, name, callback):
        self.callbacks[name] = callback


class VersionedHookTests(unittest.TestCase):
    def test_parallel_same_name_tools_without_hook_ids_remain_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ActivityRuntime(Path(tmp) / "cultivation.json")
            runner = ServerRunner(activity_runtime=runtime, bootstrap=lambda: None)
            runner.start(host="127.0.0.1", port=0)
            ctx = HookContext()
            try:
                register_hooks(ctx, server_url=runner.base_url)
                ctx.callbacks["pre_tool_call"](tool_name="read_file")
                ctx.callbacks["pre_tool_call"](tool_name="read_file")
                both = get_json(runner.base_url + "/state")
                ctx.callbacks["post_tool_call"](
                    function_name="read_file", result={"ok": True}
                )
                one = get_json(runner.base_url + "/state")
            finally:
                runner.stop()

        self.assertEqual(2, both["in_flight"]["tools"])
        self.assertEqual(1, one["in_flight"]["tools"])

    def test_documented_hooks_emit_normalized_activity_and_tolerate_extra_kwargs(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ActivityRuntime(Path(tmp) / "cultivation.json")
            runner = ServerRunner(activity_runtime=runtime, bootstrap=lambda: None)
            runner.start(host="127.0.0.1", port=0)
            ctx = HookContext()
            try:
                register_hooks(ctx, server_url=runner.base_url)
                ctx.callbacks["pre_llm_call"](session_id="turn-1", future_field=True)
                ctx.callbacks["pre_tool_call"](
                    tool_name="read_file", tool_call_id="call-1", future_field=True
                )
                ctx.callbacks["post_tool_call"](
                    function_name="read_file", tool_call_id="call-1",
                    result={"ok": True}, future_field=True,
                )
                ctx.callbacks["pre_tool_call"](
                    tool_name="terminal", tool_call_id="call-2"
                )
                ctx.callbacks["post_tool_call"](
                    function_name="terminal", tool_call_id="call-2",
                    result="unstructured output",
                )
                ctx.callbacks["pre_tool_call"](
                    tool_name="terminal", tool_call_id="call-3"
                )
                ctx.callbacks["post_tool_call"](
                    function_name="terminal", tool_call_id="call-3",
                    result={"ok": False, "error": "boom"},
                )
                ctx.callbacks["pre_approval_request"](
                    approval_id="approval-1", approval_mode="human"
                )
                self.assertEqual("waiting", get_json(runner.base_url + "/state")["state"])
                ctx.callbacks["post_approval_response"](
                    approval_id="approval-1", decision="denied"
                )
                ctx.callbacks["subagent_start"](subagent_id="sub-1")
                ctx.callbacks["subagent_stop"](subagent_id="sub-1", outcome="completed")
                ctx.callbacks["on_session_end"](session_id="turn-1", interrupted=True)
                cultivation = get_json(runner.base_url + "/cultivation")
            finally:
                runner.stop()

        self.assertEqual({
            "pre_llm_call", "pre_tool_call", "post_tool_call",
            "pre_approval_request", "post_approval_response", "on_session_end",
            "subagent_start", "subagent_stop",
        }, set(ctx.callbacks))
        self.assertEqual(1, cultivation["counters"]["tool_success_total"])
        self.assertEqual(1, cultivation["counters"]["tool_failed_total"])

    def test_denied_approval_neutralizes_the_following_tool_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ActivityRuntime(Path(tmp) / "cultivation.json")
            runner = ServerRunner(activity_runtime=runtime, bootstrap=lambda: None)
            runner.start(host="127.0.0.1", port=0)
            ctx = HookContext()
            try:
                register_hooks(ctx, server_url=runner.base_url)
                for suffix, decision in (("denied", "denied"), ("timeout", "timeout")):
                    tool_id = f"blocked-tool-{suffix}"
                    approval_id = f"approval-{suffix}"
                    ctx.callbacks["pre_tool_call"](
                        tool_name="terminal", tool_call_id=tool_id
                    )
                    ctx.callbacks["pre_approval_request"](
                        approval_id=approval_id, approval_mode="human",
                        tool_call_id=tool_id,
                    )
                    ctx.callbacks["post_approval_response"](
                        approval_id=approval_id, decision=decision,
                        tool_call_id=tool_id,
                    )
                    ctx.callbacks["post_tool_call"](
                        function_name="terminal", tool_call_id=tool_id,
                        result={"ok": False, "error": "permission denied"},
                    )
                activity = get_json(runner.base_url + "/state")
                cultivation = get_json(runner.base_url + "/cultivation")
            finally:
                runner.stop()

        self.assertEqual("unknown", activity["state"])
        self.assertEqual(0, cultivation["counters"]["tool_failed_total"])

    def test_parallel_idless_lifecycles_remain_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ActivityRuntime(Path(tmp) / "cultivation.json")
            runner = ServerRunner(activity_runtime=runtime, bootstrap=lambda: None)
            runner.start(host="127.0.0.1", port=0)
            ctx = HookContext()
            try:
                register_hooks(ctx, server_url=runner.base_url)

                ctx.callbacks["pre_approval_request"](approval_mode="human")
                ctx.callbacks["pre_approval_request"](approval_mode="human")
                approvals_two = get_json(runner.base_url + "/state")
                ctx.callbacks["post_approval_response"](decision="approved")
                approvals_one = get_json(runner.base_url + "/state")

                ctx.callbacks["pre_llm_call"]()
                ctx.callbacks["pre_llm_call"]()
                turns_two = get_json(runner.base_url + "/state")
                ctx.callbacks["on_session_end"]()
                turns_one = get_json(runner.base_url + "/state")

                ctx.callbacks["subagent_start"]()
                ctx.callbacks["subagent_start"]()
                subagents_two = get_json(runner.base_url + "/state")
                ctx.callbacks["subagent_stop"]()
                subagents_one = get_json(runner.base_url + "/state")
            finally:
                runner.stop()

        self.assertEqual(2, approvals_two["in_flight"]["approvals"])
        self.assertEqual(1, approvals_one["in_flight"]["approvals"])
        self.assertEqual(2, turns_two["in_flight"]["turns"])
        self.assertEqual(1, turns_one["in_flight"]["turns"])
        self.assertEqual(2, subagents_two["in_flight"]["subagents"])
        self.assertEqual(1, subagents_one["in_flight"]["subagents"])


if __name__ == "__main__":
    unittest.main()
