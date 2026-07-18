import json
import os
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from clawchat_pet.activity import ActivityRuntime
from clawchat_pet.server import ServerRunner
from clawchat_pet.simulator import default_save

TEST_PETS = [{
    "slug": "yinyue-2", "displayName": "Pet", "source": "petdex",
    "assetKind": "sprite", "cached": True,
    "spriteUrl": "/api/v1/pets/yinyue-2/sprite.png",
}]


def post_json(url: str, payload: dict):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=1) as response:
        return response.status, json.load(response)


def get_json(url: str):
    with urllib.request.urlopen(url, timeout=1) as response:
        return json.load(response)


class ActivityRuntimeHTTPTests(unittest.TestCase):
    @staticmethod
    def event(event_id: str, occurred_at: float, kind: str, **payload):
        return {
            "schema_version": 1,
            "event_id": event_id,
            "occurred_at": occurred_at,
            "kind": kind,
            "payload": payload,
        }

    def test_versioned_tool_start_is_accepted_once_and_legacy_payload_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ActivityRuntime(
                Path(tmp) / "cultivation.json", pet_catalog=TEST_PETS
            )
            runner = ServerRunner(
                activity_runtime=runtime,
                bootstrap=lambda: None,
            )
            runner.start(host="127.0.0.1", port=0)
            try:
                event = {
                    "schema_version": 1,
                    "event_id": "tool-start-1",
                    "occurred_at": 200.0,
                    "kind": "tool_started",
                    "payload": {"activity_id": "call-1", "tool_name": "read_file"},
                }
                first_status, first = post_json(runner.base_url + "/api/v1/events", event)
                duplicate_status, duplicate = post_json(runner.base_url + "/api/v1/events", event)
                state = get_json(runner.base_url + "/state")
                with self.assertRaises(urllib.error.HTTPError) as rejected:
                    post_json(runner.base_url + "/api/v1/events", {"state": "run", "event_id": "legacy"})
                with self.assertRaises(urllib.error.HTTPError) as removed_alias:
                    post_json(runner.base_url + "/hook/event", event)
            finally:
                runner.stop()

        self.assertEqual((200, {"ok": True, "status": "accepted"}), (first_status, first))
        self.assertEqual((200, {"ok": True, "status": "duplicate"}), (duplicate_status, duplicate))
        self.assertEqual("run", state["state"])
        self.assertEqual(1, state["in_flight"]["tools"])
        self.assertEqual(400, rejected.exception.code)
        self.assertEqual(404, removed_alias.exception.code)

    def test_parallel_tools_settle_independently_with_three_state_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ActivityRuntime(
                Path(tmp) / "cultivation.json", pet_catalog=TEST_PETS
            )
            runner = ServerRunner(activity_runtime=runtime, bootstrap=lambda: None)
            runner.start(host="127.0.0.1", port=0)
            try:
                post_json(runner.base_url + "/api/v1/events", self.event(
                    "start-a", 200, "tool_started", activity_id="a", tool_name="read_file"
                ))
                post_json(runner.base_url + "/api/v1/events", self.event(
                    "start-b", 201, "tool_started", activity_id="b", tool_name="terminal"
                ))
                _, success = post_json(runner.base_url + "/api/v1/events", self.event(
                    "finish-b", 100, "tool_completed", activity_id="b",
                    tool_name="terminal", outcome="success"
                ))
                while_a_runs = get_json(runner.base_url + "/state")
                cultivation_after_success = get_json(runner.base_url + "/cultivation")
                _, duplicate = post_json(runner.base_url + "/api/v1/events", self.event(
                    "finish-b", 100, "tool_completed", activity_id="b",
                    tool_name="terminal", outcome="success"
                ))
                post_json(runner.base_url + "/api/v1/events", self.event(
                    "finish-a", 202, "tool_completed", activity_id="a",
                    tool_name="read_file", outcome="unknown"
                ))
                finished = get_json(runner.base_url + "/state")
                cultivation_finished = get_json(runner.base_url + "/cultivation")
            finally:
                runner.stop()

        self.assertEqual("accepted", success["status"])
        self.assertEqual("run", while_a_runs["state"])
        self.assertEqual(1, while_a_runs["in_flight"]["tools"])
        self.assertEqual(1, cultivation_after_success["counters"]["tool_success_total"])
        self.assertEqual("duplicate", duplicate["status"])
        self.assertEqual("unknown", finished["state"])
        self.assertEqual(0, finished["in_flight"]["tools"])
        self.assertEqual(1, cultivation_finished["counters"]["tool_success_total"])
        self.assertEqual(0, cultivation_finished["counters"]["tool_failed_total"])

    def test_approval_turn_and_subagent_lifecycles_follow_activity_priority(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ActivityRuntime(
                Path(tmp) / "cultivation.json", pet_catalog=TEST_PETS
            )
            runner = ServerRunner(activity_runtime=runtime, bootstrap=lambda: None)
            runner.start(host="127.0.0.1", port=0)
            send = lambda event: post_json(runner.base_url + "/api/v1/events", event)
            try:
                send(self.event("smart-0", 0, "approval_requested", activity_id="smart-0", mode="smart"))
                self.assertEqual("review", get_json(runner.base_url + "/state")["state"])
                send(self.event("smart-0-end", 0.5, "approval_resolved", activity_id="smart-0", decision="approved"))
                send(self.event("turn-1", 1, "turn_started", activity_id="turn"))
                self.assertEqual("review", get_json(runner.base_url + "/state")["state"])
                send(self.event("sub-1", 2, "subagent_started", activity_id="sub"))
                self.assertEqual("subagent", get_json(runner.base_url + "/state")["state"])
                send(self.event("tool-1", 3, "tool_started", activity_id="tool", tool_name="delegate_task"))
                self.assertEqual("run", get_json(runner.base_url + "/state")["state"])
                send(self.event("approval-1", 4, "approval_requested", activity_id="approval", mode="human"))
                self.assertEqual("waiting", get_json(runner.base_url + "/state")["state"])
                send(self.event("approval-2", 5, "approval_resolved", activity_id="approval", decision="denied"))
                self.assertEqual("run", get_json(runner.base_url + "/state")["state"])
                send(self.event("tool-2", 6, "tool_completed", activity_id="tool", tool_name="delegate_task", outcome="success"))
                self.assertEqual("subagent", get_json(runner.base_url + "/state")["state"])
                send(self.event("sub-2", 7, "subagent_stopped", activity_id="sub", outcome="completed"))
                send(self.event("turn-2", 8, "turn_ended", activity_id="turn", outcome="interrupted"))
                cultivation = get_json(runner.base_url + "/cultivation")

                send(self.event("smart-1", 9, "approval_requested", activity_id="smart", mode="smart"))
                smart_state = get_json(runner.base_url + "/state")
                send(self.event("smart-2", 10, "approval_resolved", activity_id="smart", decision="approved"))
            finally:
                runner.stop()

        self.assertEqual(1, cultivation["counters"]["tool_success_total"])
        self.assertEqual(0, cultivation["counters"]["tool_failed_total"])
        self.assertEqual("wave", smart_state["state"])

    def test_persistence_failure_commits_neither_cultivation_nor_activity(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp)
            runtime = ActivityRuntime(
                runtime_dir / "cultivation.json", pet_catalog=TEST_PETS
            )
            runner = ServerRunner(activity_runtime=runtime, bootstrap=lambda: None)
            runner.start(host="127.0.0.1", port=0)
            try:
                post_json(runner.base_url + "/api/v1/events", self.event(
                    "start", 1, "tool_started", activity_id="tool", tool_name="read_file"
                ))
                os.chmod(runtime_dir, 0o500)
                try:
                    with self.assertRaises(urllib.error.HTTPError) as failed:
                        post_json(runner.base_url + "/api/v1/events", self.event(
                            "finish", 2, "tool_completed", activity_id="tool",
                            tool_name="read_file", outcome="success"
                        ))
                    state = get_json(runner.base_url + "/state")
                    cultivation = get_json(runner.base_url + "/cultivation")
                finally:
                    os.chmod(runtime_dir, 0o700)
            finally:
                runner.stop()

        self.assertEqual(500, failed.exception.code)
        self.assertEqual("run", state["state"])
        self.assertEqual(0, cultivation["counters"]["tool_success_total"])

    def test_restart_forgets_transient_activity_and_recent_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            save = Path(tmp) / "cultivation.json"
            first = ActivityRuntime(save, pet_catalog=TEST_PETS)
            first.ingest(self.event(
                "start", 1, "tool_started", activity_id="tool", tool_name="read_file"
            ))
            restarted = ActivityRuntime(save, pet_catalog=TEST_PETS)

        self.assertEqual("run", first.activity_state()["state"])
        self.assertEqual("idle", restarted.activity_state()["state"])

    def test_success_runs_the_complete_cultivation_transition_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            save_file = Path(tmp) / "cultivation.json"
            save = default_save()
            save["stats"]["qi"] = 29.0
            save_file.write_text(json.dumps(save), encoding="utf-8")
            runtime = ActivityRuntime(save_file, pet_catalog=TEST_PETS)
            runner = ServerRunner(activity_runtime=runtime, bootstrap=lambda: None)
            runner.start(host="127.0.0.1", port=0)
            try:
                post_json(runner.base_url + "/api/v1/events", self.event(
                    "success", 1, "tool_completed", activity_id="tool",
                    tool_name="read_file", outcome="success"
                ))
                cultivation = get_json(runner.base_url + "/cultivation")
            finally:
                runner.stop()

        self.assertEqual("lianqi-2", cultivation["realm"]["key"])
        self.assertEqual(0.0, cultivation["stats"]["qi"])
        self.assertLessEqual(cultivation["stats"]["qi"], cultivation["stats"]["max_qi"])

    def test_event_id_remains_duplicate_after_more_than_two_hundred_later_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ActivityRuntime(
                Path(tmp) / "cultivation.json", pet_catalog=TEST_PETS
            )
            first = self.event(
                "durable-success", 1, "tool_completed", activity_id="tool",
                tool_name="read_file", outcome="success"
            )
            self.assertEqual("accepted", runtime.ingest(first))
            for index in range(201):
                runtime.ingest(self.event(
                    f"turn-{index}", index + 2, "turn_started",
                    activity_id=f"turn-{index}",
                ))
            replay = runtime.ingest(first)
            cultivation = runtime.cultivation_state()

        self.assertEqual("duplicate", replay)
        self.assertEqual(1, cultivation["counters"]["tool_success_total"])

    def test_policy_and_log_share_the_server_runtime_store_with_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = ActivityRuntime(
                Path(tmp) / "cultivation.json", pet_catalog=TEST_PETS
            )
            runner = ServerRunner(activity_runtime=runtime, bootstrap=lambda: None)
            runner.start(host="127.0.0.1", port=0)
            try:
                post_json(runner.base_url + "/api/v1/events", self.event(
                    "success", 1, "tool_completed", activity_id="tool",
                    tool_name="read_file", outcome="success",
                ))
                _, changed = post_json(
                    runner.base_url + "/api/v1/policy",
                    {"name": "冲关", "source": "test"},
                )
                policy = get_json(runner.base_url + "/api/v1/policy")
                cultivation = get_json(runner.base_url + "/cultivation")
                event_log = get_json(runner.base_url + "/cultivation/log")
            finally:
                runner.stop()

        self.assertEqual("冲关", changed["policy"]["name"])
        self.assertEqual("冲关", policy["policy"]["name"])
        self.assertEqual("冲关", cultivation["policy"]["name"])
        self.assertEqual(1, cultivation["counters"]["tool_success_total"])
        self.assertTrue(any(
            event["type"] == "tool_success" for event in event_log["events"]
        ))


if __name__ == "__main__":
    unittest.main()
