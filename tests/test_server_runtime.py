import http.server
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from clawchat_pet.server import ServerRunner


class HealthyLookalikeHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        body = json.dumps({"ok": True, "service": "clawchat-pet"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.send_response(204)
        self.end_headers()


class ServerRuntimeTests(unittest.TestCase):
    def test_health_is_available_while_runtime_bootstrap_is_still_warming(self):
        with tempfile.TemporaryDirectory() as tmp:
            bootstrap_started = threading.Event()
            release_bootstrap = threading.Event()

            def slow_bootstrap():
                bootstrap_started.set()
                release_bootstrap.wait(timeout=2)

            runner = ServerRunner(
                runtime_dir=Path(tmp),
                bootstrap=slow_bootstrap,
            )
            start_thread = threading.Thread(
                target=lambda: runner.start(host="127.0.0.1", port=0),
                daemon=True,
            )
            start_thread.start()
            try:
                self.assertTrue(bootstrap_started.wait(timeout=1))
                with urllib.request.urlopen(
                    runner.base_url + "/healthz", timeout=0.2
                ) as response:
                    health = json.load(response)
                start_thread.join(timeout=0.2)
                self.assertFalse(
                    start_thread.is_alive(),
                    "server start must not wait for pet warm-up",
                )
            finally:
                release_bootstrap.set()
                start_thread.join(timeout=2)
                runner.stop()

        self.assertEqual("clawchat-pet", health["service"])

    def test_runtime_serves_health_and_state_from_an_isolated_ephemeral_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp)
            (runtime_dir / "pet_state.json").write_text(
                json.dumps({"state": "run", "reason": "integration-test", "ts": 4102444800}),
                encoding="utf-8",
            )
            runner = ServerRunner(runtime_dir=runtime_dir, bootstrap=lambda: None)

            runner.start(host="127.0.0.1", port=0)
            try:
                with urllib.request.urlopen(runner.base_url + "/healthz", timeout=1) as response:
                    health = json.load(response)
                with urllib.request.urlopen(runner.base_url + "/state", timeout=1) as response:
                    state = json.load(response)
            finally:
                runner.stop()

        self.assertEqual({"ok": True, "service": "clawchat-pet"}, {
            "ok": health["ok"],
            "service": health["service"],
        })
        self.assertEqual("idle", state["state"])
        self.assertEqual("no activity", state["reason"])

    def test_repeated_start_keeps_one_owned_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = ServerRunner(
                runtime_dir=Path(tmp),
                bootstrap=lambda: None,
            )
            try:
                started = runner.start(host="127.0.0.1", port=0)
                original_url = runner.base_url
                started_again = runner.start(host="127.0.0.1", port=0)
                repeated_url = runner.base_url
            finally:
                runner.stop()

        self.assertTrue(started)
        self.assertFalse(started_again)
        self.assertEqual(original_url, repeated_url)

    def test_plugin_fails_when_a_healthy_lookalike_already_owns_its_port(self):
        lookalike = http.server.ThreadingHTTPServer(("127.0.0.1", 0), HealthyLookalikeHandler)
        thread = threading.Thread(target=lookalike.serve_forever, daemon=True)
        thread.start()
        port = lookalike.server_address[1]
        repo_root = Path(__file__).resolve().parents[1]
        script = """
import importlib.util
from pathlib import Path

class Context:
    def register_hook(self, name, callback):
        pass

    def register_skill(self, name, path, description=None):
        pass

path = Path.cwd() / "__init__.py"
spec = importlib.util.spec_from_file_location("clawchat_pet_plugin_port_test", path)
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)
plugin.register(Context())
"""
        try:
            with tempfile.TemporaryDirectory() as tmp:
                env = os.environ.copy()
                env.update({
                    "CLAWCHAT_PET_HOST": "127.0.0.1",
                    "CLAWCHAT_PET_PORT": str(port),
                    "HERMES_HOME": tmp,
                    "PYTHONPATH": str(repo_root),
                })
                result = subprocess.run(
                    [sys.executable, "-c", script],
                    cwd=repo_root,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

            with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1) as response:
                original_service = json.load(response)
        finally:
            lookalike.shutdown()
            lookalike.server_close()
            thread.join(timeout=1)

        self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("Address already in use", result.stderr)
        self.assertEqual("clawchat-pet", original_service["service"])

    def test_repeated_plugin_registration_serves_until_hermes_exits(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]

        repo_root = Path(__file__).resolve().parents[1]
        script = """
import importlib.util
import sys
from pathlib import Path

class Context:
    def register_hook(self, name, callback):
        pass

    def register_skill(self, name, path, description=None):
        pass

path = Path.cwd() / "__init__.py"
spec = importlib.util.spec_from_file_location("clawchat_pet_plugin_lifecycle_test", path)
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)
ctx = Context()
plugin.register(ctx)
plugin.register(ctx)
print("READY", flush=True)
sys.stdin.readline()
"""
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env.update({
                "CLAWCHAT_PET_HOST": "127.0.0.1",
                "CLAWCHAT_PET_PORT": str(port),
                "HERMES_HOME": tmp,
                "PYTHONPATH": str(repo_root),
            })
            process = subprocess.Popen(
                [sys.executable, "-c", script],
                cwd=repo_root,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                deadline = time.monotonic() + 5
                health = None
                while time.monotonic() < deadline:
                    try:
                        with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=0.2) as response:
                            health = json.load(response)
                        break
                    except OSError:
                        if process.poll() is not None:
                            break
                        time.sleep(0.05)

                self.assertIsNotNone(health)
                self.assertEqual("clawchat-pet", health["service"])
                assert process.stdin is not None
                process.stdin.write("\n")
                process.stdin.flush()
                stdout, stderr = process.communicate(timeout=5)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=2)

        self.assertEqual(0, process.returncode, stdout + stderr)
        with self.assertRaises(OSError):
            urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=0.2)


if __name__ == "__main__":
    unittest.main()
