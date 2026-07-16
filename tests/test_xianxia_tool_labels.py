import unittest

from clawchat_pet.simulator import apply_event, default_save, public_state


class XianxiaToolLabelTests(unittest.TestCase):
    def test_success_log_uses_xianxia_name_instead_of_raw_tool_name(self):
        save = default_save()
        apply_event(save, {"state": "wave", "tool": "read_file", "ts": 10, "event_id": "success-1"})

        text = save["event_log"][-1]["text"]
        self.assertIn("天机推演", text)
        self.assertNotIn("read_file", text)

    def test_failure_log_hides_unknown_raw_tool_name(self):
        save = default_save()
        apply_event(save, {"state": "failed", "tool": "future_tool", "ts": 10, "event_id": "failed-1"})

        text = save["event_log"][-1]["text"]
        self.assertIn("无名术法", text)
        self.assertNotIn("future_tool", text)

    def test_public_state_sanitizes_existing_log_entries(self):
        save = default_save()
        save["event_log"].append({
            "ts": 10,
            "type": "tool_success",
            "text": "历练功成：read_file，灵气 +2.4。",
        })

        state = public_state(save)
        text = state["event_log"][-1]["text"]
        self.assertIn("天机推演", text)
        self.assertNotIn("read_file", text)

    def test_public_state_preserves_already_translated_log_entries(self):
        save = default_save()
        save["event_log"].append({
            "ts": 10,
            "type": "tool_success",
            "text": "历练功成：天机推演，灵气 +2.4。",
        })

        state = public_state(save)
        self.assertEqual("历练功成：天机推演，灵气 +2.4。", state["event_log"][-1]["text"])

    def test_public_state_translates_current_and_recent_tool_names(self):
        save = default_save()
        apply_event(save, {"state": "run", "tool": "search_files", "ts": 10, "event_id": "run-1"})

        state = public_state(save)
        self.assertEqual("天机推演", state["state"]["current_tool"])
        self.assertEqual("天机推演", state["recent_window"]["events"][-1]["tool"])
        self.assertNotIn("search_files", str(state["state"]))
        self.assertNotIn("search_files", str(state["recent_window"]))


if __name__ == "__main__":
    unittest.main()
