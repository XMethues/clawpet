import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from clawchat_pet.liveware import LivewareAgentRunner


def load_plugin_entrypoint():
    path = Path(__file__).resolve().parents[1] / "__init__.py"
    spec = importlib.util.spec_from_file_location("clawchat_pet_plugin_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class LivewareAgentRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.binary = self.home / "clawchat" / "liveware" / "liveware"
        self.binary.parent.mkdir(parents=True)
        self.binary.write_bytes(b"binary")
        self.runner = LivewareAgentRunner(self.home)

    def tearDown(self):
        self.runner.stop()
        self.tmp.cleanup()

    @patch("clawchat_pet.liveware.subprocess.Popen")
    def test_ensure_starts_liveware_agent(self, popen):
        proc = Mock(pid=1234)
        proc.poll.return_value = None
        popen.return_value = proc

        started = self.runner.ensure_running()

        self.assertTrue(started)
        self.assertEqual(popen.call_args.args[0], [str(self.binary), "agent"])
        self.assertEqual(self.runner.pid_file.read_text(), "1234\n")

    @patch("clawchat_pet.liveware.subprocess.Popen")
    def test_ensure_is_idempotent_for_owned_process(self, popen):
        proc = Mock(pid=1234)
        proc.poll.return_value = None
        popen.return_value = proc

        self.runner.ensure_running()
        started_again = self.runner.ensure_running()

        self.assertFalse(started_again)
        popen.assert_called_once()

    @patch("clawchat_pet.liveware.subprocess.Popen")
    def test_stop_terminates_only_process_started_by_runner(self, popen):
        proc = Mock(pid=1234)
        proc.poll.return_value = None
        popen.return_value = proc
        self.runner.ensure_running()

        self.runner.stop()

        proc.terminate.assert_called_once()
        proc.wait.assert_called_once()
        self.assertFalse(self.runner.pid_file.exists())

    @patch("clawchat_pet.liveware.os.kill")
    @patch("clawchat_pet.liveware.subprocess.Popen")
    def test_ensure_takes_over_agent_recorded_by_previous_plugin_process(self, popen, kill):
        self.runner.runtime_dir.mkdir(parents=True)
        self.runner.pid_file.write_text("4321\n")
        proc = Mock(pid=5678)
        proc.poll.return_value = None
        popen.return_value = proc
        with patch.object(
            self.runner,
            "_pid_is_liveware_agent",
            return_value=True,
        ):
            started = self.runner.ensure_running()

        self.assertTrue(started)
        kill.assert_called_once_with(4321, 15)
        self.assertEqual(self.runner.pid_file.read_text(), "5678\n")

    @patch("clawchat_pet.liveware.subprocess.Popen")
    def test_ensure_replaces_stale_pid_record(self, popen):
        self.runner.runtime_dir.mkdir(parents=True)
        self.runner.pid_file.write_text("4321\n")
        proc = Mock(pid=5678)
        proc.poll.return_value = None
        popen.return_value = proc
        with patch.object(
            self.runner,
            "_pid_is_liveware_agent",
            return_value=False,
        ):
            started = self.runner.ensure_running()

        self.assertTrue(started)
        self.assertEqual(self.runner.pid_file.read_text(), "5678\n")


class PluginRegistrationTests(unittest.TestCase):
    def test_register_starts_pet_server_and_liveware(self):
        plugin = load_plugin_entrypoint()
        ctx = Mock()
        with (
            patch.object(plugin, "_ensure_server_running") as pet_start,
            patch.object(plugin, "_start_liveware_publication") as publication_start,
            patch("clawchat_pet.liveware.ensure_running") as liveware_start,
            patch("clawchat_pet.server.get_runtime", return_value=Mock()),
        ):
            plugin.register(ctx)

        pet_start.assert_called_once_with()
        liveware_start.assert_called_once_with()
        publication_start.assert_called_once_with()

    def test_register_schedules_clawpet_publication_during_startup(self):
        plugin = load_plugin_entrypoint()
        ctx = Mock()
        threads = []

        class CapturedThread:
            def __init__(self, *, target, name, daemon):
                self.target = target
                self.name = name
                self.daemon = daemon
                self.started = False
                threads.append(self)

            def start(self):
                self.started = True

            def is_alive(self):
                return self.started

        with (
            patch.object(plugin, "_ensure_server_running"),
            patch("clawchat_pet.liveware.ensure_running"),
            patch("clawchat_pet.server.get_runtime", return_value=Mock()),
            patch("threading.Thread", CapturedThread),
        ):
            plugin.register(ctx)

        self.assertEqual(1, len(threads))
        self.assertEqual("clawchat-pet-publication", threads[0].name)
        self.assertTrue(threads[0].daemon)
        self.assertTrue(threads[0].started)

    def test_publication_failure_does_not_block_gateway_startup(self):
        plugin = load_plugin_entrypoint()
        ctx = Mock()

        class ImmediateThread:
            def __init__(self, *, target, name, daemon):
                self.target = target

            def start(self):
                self.target()

            def is_alive(self):
                return False

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.dict(os.environ, {"HERMES_HOME": tmp}),
                patch.object(plugin, "_ensure_server_running"),
                patch("clawchat_pet.liveware.ensure_running") as liveware_start,
                patch("clawchat_pet.server.get_runtime", return_value=Mock()),
                patch("threading.Thread", ImmediateThread),
                self.assertLogs("clawchat-pet", level="ERROR") as logs,
            ):
                plugin.register(ctx)

        self.assertEqual(2, liveware_start.call_count)
        self.assertTrue(any(
            "publication startup failed" in entry for entry in logs.output
        ))


if __name__ == "__main__":
    unittest.main()
