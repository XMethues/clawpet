import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from clawchat_pet import gateway_startup, liveware
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
    def test_register_starts_pet_server_and_installs_gateway_hook(self):
        plugin = load_plugin_entrypoint()
        ctx = Mock()
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.dict(os.environ, {"HERMES_HOME": tmp}),
                patch.object(plugin, "_ensure_server_running") as pet_start,
                patch("clawchat_pet.liveware.ensure_running") as liveware_start,
                patch(
                    "clawchat_pet.publication.LivewarePublication.ensure"
                ) as publication_start,
                patch("clawchat_pet.server.get_runtime", return_value=Mock()),
            ):
                plugin.register(ctx)
                installed = Path(tmp) / "hooks" / gateway_startup.HOOK_NAME

                self.assertEqual("1", os.environ[gateway_startup.PLUGIN_ACTIVE_ENV])
                self.assertEqual(
                    {"HOOK.yaml", "handler.py"},
                    {path.name for path in installed.iterdir()},
                )

        pet_start.assert_called_once_with()
        liveware_start.assert_not_called()
        publication_start.assert_not_called()

    def test_gateway_startup_schedules_liveware_publication_once(self):
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
            patch.object(gateway_startup, "_STARTUP_THREAD", None),
            patch.object(gateway_startup, "_LIVEWARE_ATEXIT_REGISTERED", False),
            patch("clawchat_pet.gateway_startup.atexit.register") as register_exit,
            patch("clawchat_pet.gateway_startup.threading.Thread", CapturedThread),
        ):
            first = gateway_startup.handle_gateway_startup(
                "gateway:startup",
                {"platforms": ["clawchat"]},
            )
            repeated = gateway_startup.handle_gateway_startup(
                "gateway:startup",
                {"platforms": ["clawchat"]},
            )

        self.assertTrue(first)
        self.assertFalse(repeated)
        self.assertEqual(1, len(threads))
        self.assertEqual("clawchat-pet-liveware-startup", threads[0].name)
        self.assertTrue(threads[0].daemon)
        self.assertTrue(threads[0].started)
        register_exit.assert_called_once_with(liveware.stop)

    def test_gateway_startup_repairs_publication_between_agent_attempts(self):
        class ImmediateThread:
            def __init__(self, *, target, name, daemon):
                self.target = target

            def start(self):
                self.target()

            def is_alive(self):
                return False

        publication = Mock()
        publication.ensure.return_value = Mock(app_id="app-1", url="https://pet")
        with (
            patch.object(gateway_startup, "_STARTUP_THREAD", None),
            patch.object(gateway_startup, "_LIVEWARE_ATEXIT_REGISTERED", False),
            patch.object(
                gateway_startup, "_ensure_current_pet_asset"
            ) as ensure_pet,
            patch.object(gateway_startup, "_ensure_liveware_running") as ensure_agent,
            patch("clawchat_pet.gateway_startup.atexit.register"),
            patch("clawchat_pet.gateway_startup.threading.Thread", ImmediateThread),
            patch(
                "clawchat_pet.publication.HermesLivewareAdapter"
            ) as adapter_type,
            patch(
                "clawchat_pet.publication.LivewarePublication",
                return_value=publication,
            ) as publication_type,
        ):
            scheduled = gateway_startup.handle_gateway_startup(
                "gateway:startup",
                {"platforms": ["clawchat"]},
            )

        self.assertTrue(scheduled)
        ensure_pet.assert_called_once_with()
        self.assertEqual(2, ensure_agent.call_count)
        publication_type.assert_called_once_with(adapter_type.return_value)
        publication.ensure.assert_called_once_with()

    def test_gateway_caches_current_pet_before_starting_liveware(self):
        class ImmediateThread:
            def __init__(self, *, target, name, daemon):
                self.target = target

            def start(self):
                self.target()

            def is_alive(self):
                return False

        events = []
        runtime = Mock()
        runtime.ensure_current_pet_asset.side_effect = (
            lambda: events.append("pet-ready")
        )
        publication = Mock()
        publication.ensure.side_effect = lambda: (
            events.append("publication"),
            Mock(app_id="app-1", url="https://pet"),
        )[1]

        with (
            patch.object(gateway_startup, "_STARTUP_THREAD", None),
            patch.object(gateway_startup, "_LIVEWARE_ATEXIT_REGISTERED", False),
            patch.object(
                gateway_startup,
                "_ensure_liveware_running",
                side_effect=lambda: events.append("liveware"),
            ),
            patch("clawchat_pet.gateway_startup.atexit.register"),
            patch("clawchat_pet.gateway_startup.threading.Thread", ImmediateThread),
            patch("clawchat_pet.server.get_runtime", return_value=runtime),
            patch("clawchat_pet.publication.HermesLivewareAdapter"),
            patch(
                "clawchat_pet.publication.LivewarePublication",
                return_value=publication,
            ),
        ):
            scheduled = gateway_startup.handle_gateway_startup(
                "gateway:startup",
                {"platforms": ["clawchat"]},
            )

        self.assertTrue(scheduled)
        self.assertEqual(
            ["pet-ready", "liveware", "publication", "liveware"],
            events,
        )

    def test_missing_current_pet_prevents_liveware_publication(self):
        class ImmediateThread:
            def __init__(self, *, target, name, daemon):
                self.target = target

            def start(self):
                self.target()

            def is_alive(self):
                return False

        publication = Mock()
        with (
            patch.object(gateway_startup, "_STARTUP_THREAD", None),
            patch.object(gateway_startup, "_LIVEWARE_ATEXIT_REGISTERED", False),
            patch.object(
                gateway_startup,
                "_ensure_current_pet_asset",
                side_effect=OSError("download failed"),
            ),
            patch.object(gateway_startup, "_ensure_liveware_running") as ensure_agent,
            patch("clawchat_pet.gateway_startup.atexit.register"),
            patch("clawchat_pet.gateway_startup.threading.Thread", ImmediateThread),
            patch("clawchat_pet.publication.HermesLivewareAdapter"),
            patch(
                "clawchat_pet.publication.LivewarePublication",
                return_value=publication,
            ),
            self.assertLogs("clawchat-pet", level="ERROR") as logs,
        ):
            scheduled = gateway_startup.handle_gateway_startup(
                "gateway:startup",
                {"platforms": ["clawchat"]},
            )

        self.assertTrue(scheduled)
        ensure_agent.assert_not_called()
        publication.ensure.assert_not_called()
        self.assertTrue(any(
            "current pet asset preparation failed" in entry
            for entry in logs.output
        ))

    def test_publication_failure_does_not_escape_gateway_startup_worker(self):
        class ImmediateThread:
            def __init__(self, *, target, name, daemon):
                self.target = target

            def start(self):
                self.target()

            def is_alive(self):
                return False

        publication = Mock()
        publication.ensure.side_effect = RuntimeError("offline")
        with (
            patch.object(gateway_startup, "_STARTUP_THREAD", None),
            patch.object(gateway_startup, "_LIVEWARE_ATEXIT_REGISTERED", False),
            patch.object(gateway_startup, "_ensure_current_pet_asset"),
            patch.object(gateway_startup, "_ensure_liveware_running") as ensure_agent,
            patch("clawchat_pet.gateway_startup.atexit.register"),
            patch("clawchat_pet.gateway_startup.threading.Thread", ImmediateThread),
            patch("clawchat_pet.publication.HermesLivewareAdapter"),
            patch(
                "clawchat_pet.publication.LivewarePublication",
                return_value=publication,
            ),
            self.assertLogs("clawchat-pet", level="ERROR") as logs,
        ):
            scheduled = gateway_startup.handle_gateway_startup(
                "gateway:startup",
                {"platforms": ["clawchat"]},
            )

        self.assertTrue(scheduled)
        self.assertEqual(2, ensure_agent.call_count)
        self.assertTrue(any(
            "publication startup failed" in entry for entry in logs.output
        ))

    def test_materialized_hook_delegates_only_when_plugin_is_active(self):
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {}, clear=False):
                installed = gateway_startup.install_gateway_hook(
                    repo_root,
                    hermes_home=Path(tmp),
                )
                spec = importlib.util.spec_from_file_location(
                    "clawchat_pet_gateway_hook_test",
                    installed / "handler.py",
                )
                hook = importlib.util.module_from_spec(spec)
                assert spec.loader is not None
                spec.loader.exec_module(hook)

                with patch.object(gateway_startup, "handle_gateway_startup") as handle:
                    hook.handle("gateway:startup", {"platforms": ["clawchat"]})
                    handle.assert_called_once_with(
                        "gateway:startup",
                        {"platforms": ["clawchat"]},
                    )

                    os.environ[gateway_startup.PLUGIN_ACTIVE_ENV] = "0"
                    hook.handle("gateway:startup", {"platforms": []})
                    handle.assert_called_once()


if __name__ == "__main__":
    unittest.main()
