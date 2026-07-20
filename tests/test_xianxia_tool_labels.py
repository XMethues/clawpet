import unittest

from clawchat_pet.simulator import apply_event, default_save


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

if __name__ == "__main__":
    unittest.main()
