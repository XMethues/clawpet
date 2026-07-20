"""Minimal HTTP adapter around the authoritative in-process runtime."""
from __future__ import annotations

import http.server
import json
import os
import socketserver
import sys
import threading
import time
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlparse

from .runtime import ClawchatPetRuntime


HOST = os.environ.get("CLAWCHAT_PET_HOST", "127.0.0.1")
PORT = int(os.environ.get("CLAWCHAT_PET_PORT", "54321"))
HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
WEB_ROOT = Path(__file__).resolve().parent / "web"


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "ClawchatPetHTTP/1.0"

    def log_message(self, fmt, *args):
        return

    def _send_json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str, cache: str) -> None:
        if not path.is_file():
            self._send_json({"error": "not found"}, 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(path.read_bytes())

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            raise ValueError("JSON object required")
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(body, dict):
            raise ValueError("JSON object required")
        return body

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if path != "/command":
                self._send_json({"error": "not found"}, 404)
                return
            self._send_json(self.server.runtime.command(self._body()))
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json({"error": str(exc)}, 400)
        except KeyError as exc:
            self._send_json({"error": str(exc)}, 404)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 500)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/healthz":
                self._send_json({
                    "ok": True, "service": "clawchat-pet", "ts": time.time()
                })
                return
            if path == "/presentation":
                self._send_json(self.server.runtime.presentation())
                return
            if path == "/catalog":
                self._send_json(self.server.runtime.catalog())
                return
            prefix = "/assets/pets/"
            if path.startswith(prefix) and path.endswith(".png"):
                slug = unquote(path[len(prefix):-4])
                if not slug or "/" in slug or "\\" in slug:
                    self._send_json({"error": "not found"}, 404)
                    return
                self._send_file(
                    self.server.runtime.pet_asset(slug),
                    "image/png",
                    "public, max-age=3600",
                )
                return
            if path in {"/", "/index.html"}:
                self._send_file(
                    WEB_ROOT / "index.html", "text/html; charset=utf-8", "no-store"
                )
                return
            safe = path.lstrip("/")
            if safe.startswith("assets/") and ".." not in Path(safe).parts:
                content_type = {
                    ".js": "application/javascript; charset=utf-8",
                    ".css": "text/css; charset=utf-8",
                    ".png": "image/png",
                    ".svg": "image/svg+xml",
                }.get(Path(safe).suffix.lower(), "application/octet-stream")
                self._send_file(
                    WEB_ROOT / safe,
                    content_type,
                    "public, max-age=31536000, immutable",
                )
                return
            self._send_json({"error": "not found"}, 404)
        except KeyError as exc:
            self._send_json({"error": str(exc)}, 404)
        except FileNotFoundError:
            self._send_json({"error": "not found"}, 404)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 500)


class ReusableTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address, handler_class, runtime: ClawchatPetRuntime):
        self.runtime = runtime
        super().__init__(server_address, handler_class)


def _warm_runtime(runtime: ClawchatPetRuntime) -> None:
    try:
        runtime.pet_asset("yinyue-2")
    except Exception as exc:
        print(f"clawchat-pet pet warm failed: {exc}", file=sys.stderr, flush=True)


class ServerRunner:
    def __init__(
        self,
        runtime_dir: Path = HERMES_HOME / "clawchat-pet",
        runtime: ClawchatPetRuntime | None = None,
        bootstrap: Callable[[], None] | None = None,
    ) -> None:
        self.runtime_dir = Path(runtime_dir)
        self.runtime = runtime or ClawchatPetRuntime(self.runtime_dir)
        self.bootstrap = bootstrap or (lambda: _warm_runtime(self.runtime))
        self.httpd: ReusableTCPServer | None = None
        self.thread: threading.Thread | None = None
        self.bootstrap_thread: threading.Thread | None = None
        self.lock = threading.Lock()

    @property
    def base_url(self) -> str:
        if self.httpd is None:
            raise RuntimeError("clawchat-pet server is not running")
        host, port = self.httpd.server_address[:2]
        return f"http://{host}:{port}"

    def start(self, host: str = HOST, port: int = PORT) -> bool:
        with self.lock:
            if self.thread and self.thread.is_alive():
                return False
            try:
                self.httpd = ReusableTCPServer((host, port), Handler, self.runtime)
                self.thread = threading.Thread(
                    target=self.httpd.serve_forever,
                    name="clawchat-pet-http",
                    daemon=True,
                )
                self.thread.start()
                self.bootstrap_thread = threading.Thread(
                    target=self.bootstrap,
                    name="clawchat-pet-warm",
                    daemon=True,
                )
                self.bootstrap_thread.start()
            except Exception:
                if self.httpd is not None:
                    self.httpd.server_close()
                self.httpd = None
                self.thread = None
                self.bootstrap_thread = None
                raise
            print(f"clawchat-pet listening on {self.base_url}", flush=True)
            return True

    def stop(self) -> None:
        with self.lock:
            if self.httpd is not None:
                self.httpd.shutdown()
                self.httpd.server_close()
                self.httpd = None
            self.thread = None
            self.bootstrap_thread = None


_runtime: ClawchatPetRuntime | None = None
_runner: ServerRunner | None = None


def get_runtime() -> ClawchatPetRuntime:
    global _runtime
    if _runtime is None:
        _runtime = ClawchatPetRuntime(HERMES_HOME / "clawchat-pet")
    return _runtime


def start_background() -> bool:
    global _runner
    if _runner is None:
        _runner = ServerRunner(runtime=get_runtime())
    return _runner.start()


def stop_background() -> None:
    if _runner is not None:
        _runner.stop()


def main() -> int:
    runner = ServerRunner(runtime=get_runtime())
    try:
        runner.start()
        assert runner.thread is not None
        runner.thread.join()
    except KeyboardInterrupt:
        return 0
    finally:
        runner.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
