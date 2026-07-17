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

from . import skins as skin_registry
from .activity import ActivityRuntime, EventValidationError

HOST = os.environ.get("CLAWCHAT_PET_HOST", "127.0.0.1")
PORT = int(os.environ.get("CLAWCHAT_PET_PORT", "54321"))
HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
WEB_ROOT = Path(__file__).resolve().parent / "web"


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "ClawchatPetHTTP/0.2"

    def log_message(self, fmt, *args):
        return

    def _send_json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str, cache: str = "no-store") -> None:
        if not path.is_file():
            self._send_json({"error": "not found"}, 404)
            return
        body = b"" if self.command == "HEAD" else path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _read_body_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/v1/events":
                body = self._read_body_json()
                if not isinstance(body, dict):
                    self._send_json({"ok": False, "error": "JSON object required"}, 400)
                    return
                status = self.server.activity_runtime.ingest(body)
                self._send_json({"ok": True, "status": status})
                return
            if path == "/api/v1/policy":
                body = self._read_body_json()
                name = str(body.get("name") or body.get("policy") or "").strip()
                source = str(body.get("source") or "api").strip() or "api"
                if not name:
                    self._send_json({"error": "name required"}, 400)
                    return
                try:
                    self._send_json({
                        "policy": self.server.activity_runtime.set_policy(name, source=source)
                    })
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, 400)
                return
            if path == "/api/v1/pets/current":
                body = self._read_body_json()
                slug = str(body.get("slug") or "").strip()
                if not slug:
                    self._send_json({"error": "slug required"}, 400)
                    return
                self._send_json(self.server.activity_runtime.pet_selection(slug))
                return
            pet_path = [unquote(part) for part in path.removeprefix("/api/v1/pets/").split("/") if part]
            if len(pet_path) == 2 and pet_path[1] == "personality":
                body = self._read_body_json()
                personality = self.server.activity_runtime.update_personality(pet_path[0], body)
                self._send_json({"personality": personality})
                return
            if path == "/api/v1/pets/refresh":
                from .services import petdex

                pets = petdex.list_pets(force=True)
                self._send_json({"pets": [p.to_dict() for p in pets], "count": len(pets)})
                return
            if path == "/api/v1/skins/current":
                body = self._read_body_json()
                skin_id = str(body.get("id") or body.get("skin") or "").strip()
                if not skin_id:
                    self._send_json({"error": "id required"}, 400)
                    return
                try:
                    self._send_json({"skin": skin_registry.set_current_skin(skin_id)})
                except PermissionError as exc:
                    self._send_json({"error": str(exc)}, 403)
                except KeyError as exc:
                    self._send_json({"error": str(exc)}, 404)
                return
            if path == "/api/v1/skins/create":
                body = self._read_body_json()
                if not isinstance(body, dict):
                    self._send_json({"error": "JSON object required"}, 400)
                    return
                try:
                    unlock = bool(body.get("unlock", True))
                    activate = bool(body.get("activate", False))
                    self._send_json({"skin": skin_registry.create_skin(body, unlock=unlock, activate=activate)}, 201)
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, 422)
                return
            self._send_json({"error": "not found"}, 404)
        except EventValidationError as exc:
            self._send_json({"ok": False, "error": str(exc)}, 400)
        except KeyError as exc:
            self._send_json({"error": str(exc)}, 404)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 500)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/healthz":
                self._send_json({"ok": True, "service": "clawchat-pet", "ts": time.time()})
                return
            if path in ("/state", "/api/v1/query/state"):
                self._send_json(self.server.activity_runtime.activity_state())
                return
            if path in ("/cultivation", "/api/v1/query/cultivation", "/api/v1/query/world"):
                self._send_json(self.server.activity_runtime.cultivation_state())
                return
            if path in ("/cultivation/log", "/api/v1/query/events"):
                self._send_json(self.server.activity_runtime.event_log(50))
                return
            if path in ("/voice", "/api/v1/query/voice"):
                self._send_json(self.server.activity_runtime.voice_state())
                return
            if path == "/api/v1/policy":
                self._send_json({"policy": self.server.activity_runtime.get_policy()})
                return
            if path == "/api/v1/pets":
                pets = self.server.activity_runtime.list_pets()
                self._send_json({"pets": pets, "count": len(pets)})
                return
            if path == "/api/v1/pets/current":
                self._send_json({"pet": self.server.activity_runtime.current_pet()})
                return
            if path == "/api/v1/skins":
                self._send_json(skin_registry.list_skins())
                return
            if path == "/api/v1/skins/current":
                self._send_json({"skin": skin_registry.current_skin()})
                return
            m = path.removeprefix("/api/v1/pets/")
            if m != path:
                parts = [unquote(p) for p in m.split("/") if p]
                if len(parts) == 2 and parts[1] == "personality":
                    self._send_json({
                        "personality": self.server.activity_runtime.personality(parts[0])
                    })
                    return
                from .services import petdex

                if len(parts) == 1:
                    info = petdex.ensure_cached(parts[0])
                    self._send_json({"pet": info.to_dict()})
                    return
                if len(parts) == 2 and parts[1] == "sprite.png":
                    self._send_file(petdex.sprite_path(parts[0]), "image/png", "public, max-age=3600")
                    return
            if path in ("/", "/index.html", "/yinyue-2.html"):
                self._send_file(WEB_ROOT / "index.html", "text/html; charset=utf-8")
                return
            # Vite static assets.
            safe = path.lstrip("/")
            if safe.startswith("assets/"):
                suffix = Path(safe).suffix.lower()
                ct = {
                    ".js": "application/javascript; charset=utf-8",
                    ".css": "text/css; charset=utf-8",
                    ".png": "image/png",
                    ".svg": "image/svg+xml",
                }.get(suffix, "application/octet-stream")
                self._send_file(WEB_ROOT / safe, ct, "public, max-age=31536000, immutable")
                return
            self._send_json({"error": "not found"}, 404)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 500)


class ReusableTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address, handler_class, activity_runtime: ActivityRuntime):
        self.activity_runtime = activity_runtime
        super().__init__(server_address, handler_class)


def _bootstrap_runtime() -> None:
    # Warm the default pet so the first page load has local PNG metadata.
    try:
        from .services import petdex

        petdex.current_pet()
    except Exception as exc:
        print(f"clawchat-pet pet warm failed: {exc}", file=sys.stderr, flush=True)


class ServerRunner:
    def __init__(
        self,
        runtime_dir: Path = HERMES_HOME / "clawchat-pet",
        activity_runtime: ActivityRuntime | None = None,
        bootstrap: Callable[[], None] = _bootstrap_runtime,
    ) -> None:
        self.runtime_dir = Path(runtime_dir)
        self.activity_runtime = activity_runtime or ActivityRuntime(
            self.runtime_dir / "cultivation.json"
        )
        self.bootstrap = bootstrap
        self.httpd: ReusableTCPServer | None = None
        self.thread: threading.Thread | None = None
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
                self.httpd = ReusableTCPServer(
                    (host, port), Handler, self.activity_runtime
                )
                self.bootstrap()
            except Exception:
                if self.httpd is not None:
                    self.httpd.server_close()
                    self.httpd = None
                raise
            self.thread = threading.Thread(target=self.httpd.serve_forever, name="clawchat-pet-http", daemon=True)
            self.thread.start()
            print(f"clawchat-pet listening on {self.base_url}", flush=True)
            return True

    def stop(self) -> None:
        with self.lock:
            if self.httpd is not None:
                self.httpd.shutdown()
                self.httpd.server_close()
                self.httpd = None
            self.thread = None


_runner = ServerRunner()


def start_background() -> bool:
    return _runner.start()


def stop_background() -> None:
    _runner.stop()


def main() -> int:
    try:
        from .services import petdex

        petdex.current_pet()
    except Exception as exc:
        print(f"clawchat-pet pet warm failed: {exc}", file=sys.stderr, flush=True)
    runtime = ActivityRuntime(HERMES_HOME / "clawchat-pet" / "cultivation.json")
    with ReusableTCPServer((HOST, PORT), Handler, runtime) as srv:
        print(f"clawchat-pet listening on http://{HOST}:{PORT}", flush=True)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
