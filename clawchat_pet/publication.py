"""Idempotently publish the ClawPet web experience through Liveware."""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol


APP_NAME = "ClawPet"
LOCAL_UPSTREAM = "http://127.0.0.1:54321"


class LivewareAuthenticationRequired(RuntimeError):
    """The Liveware CLI has no usable saved login."""


class PublicationError(RuntimeError):
    """ClawPet could not establish its external publication."""


class PublicationAdapter(Protocol):
    def list_liveware_apps(self) -> list[dict[str, Any]]: ...

    def login_liveware(self) -> None: ...

    def create_liveware_app(self, name: str) -> dict[str, Any]: ...

    def bind_liveware_app(self, app_id: str, upstream: str) -> str: ...

    def list_clawchat_apps(self) -> list[dict[str, Any]]: ...

    def register_clawchat_app(self, name: str, app_id: str, url: str) -> None: ...


@dataclass(frozen=True)
class PublicationResult:
    name: str
    app_id: str
    url: str


def _find_app_id(value: Any) -> str:
    if isinstance(value, Mapping):
        for key in ("app_id", "appId", "id"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        for candidate in value.values():
            found = _find_app_id(candidate)
            if found:
                return found
    return ""


class HermesLivewareAdapter:
    """Production adapter over the Liveware CLI and Hermes ClawChat tools."""

    _APP_ID = re.compile(
        r"app[ _-]?id\b\s*[:=]?\s*\"?([A-Za-z0-9][A-Za-z0-9_-]*)\"?",
        re.IGNORECASE,
    )
    _DOMAIN = re.compile(
        r"(?:^|\n)[ \t]*domain\b[ \t:=]+"
        r"([A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9])[ \t]*\r?\n",
        re.IGNORECASE,
    )
    _URL = re.compile(r"https?://[^\s\"']+")

    def __init__(
        self,
        *,
        run_cli: Callable[[list[str]], Any] | None = None,
        invoke_tool: Callable[[str, dict[str, Any]], Any] | None = None,
        binary: str | None = None,
    ) -> None:
        self._run_cli = run_cli or self._default_run_cli
        self._invoke_tool = invoke_tool or self._default_invoke_tool
        self._binary = binary or self._resolve_binary()

    @staticmethod
    def _resolve_binary() -> str:
        hermes_home = Path(
            os.environ.get("HERMES_HOME") or Path.home() / ".hermes"
        )
        local = hermes_home / "clawchat" / "liveware" / "liveware"
        if local.is_file():
            return str(local)
        return shutil.which("liveware") or str(local)

    @staticmethod
    def _default_run_cli(args: list[str]):
        try:
            return subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise PublicationError(f"Liveware command failed: {exc}") from exc

    @staticmethod
    def _default_invoke_tool(name: str, args: dict[str, Any]) -> Any:
        try:
            from tools.registry import registry
        except ImportError as exc:
            raise PublicationError("Hermes tool registry is unavailable") from exc
        entry = registry.get_entry(name)
        if entry is None:
            raise PublicationError(f"required Hermes tool is unavailable: {name}")
        result = entry.handler(args, task_id="clawchat-pet-startup")
        if inspect.isawaitable(result):
            result = asyncio.run(result)
        return result

    @staticmethod
    def _tool_payload(value: Any, name: str) -> dict[str, Any]:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError as exc:
                raise PublicationError(
                    f"{name} returned invalid JSON"
                ) from exc
        if not isinstance(value, Mapping):
            raise PublicationError(f"{name} returned an invalid result")
        payload = dict(value)
        if payload.get("error") or payload.get("ok") is False:
            detail = payload.get("message") or payload.get("error")
            raise PublicationError(f"{name} failed: {detail}")
        return payload

    def list_liveware_apps(self) -> list[dict[str, Any]]:
        result = self._run_cli([self._binary, "app", "list", "--json"])
        if result.returncode:
            raise LivewareAuthenticationRequired(
                (result.stderr or result.stdout or "liveware login required").strip()
            )
        try:
            items = json.loads(result.stdout)
        except (TypeError, ValueError) as exc:
            raise PublicationError("liveware app list returned invalid JSON") from exc
        if not isinstance(items, list):
            raise PublicationError("liveware app list returned an invalid result")
        return [dict(item) for item in items if isinstance(item, Mapping)]

    def login_liveware(self) -> None:
        payload = self._tool_payload(
            self._invoke_tool("clawchat_liveware_login", {}),
            "clawchat_liveware_login",
        )
        if payload.get("ok") is not True:
            raise PublicationError("clawchat_liveware_login did not confirm login")

    def create_liveware_app(self, name: str) -> dict[str, Any]:
        result = self._run_cli([self._binary, "app", "create", name])
        if result.returncode:
            detail = (result.stderr or result.stdout or "unknown error").strip()
            raise PublicationError(f"liveware app create failed: {detail}")
        app_id = ""
        try:
            app_id = _find_app_id(json.loads(result.stdout))
        except (TypeError, ValueError):
            match = self._APP_ID.search(result.stdout or "")
            app_id = match.group(1) if match else ""
        if not app_id:
            raise PublicationError("liveware app create returned no app id")
        return {"app_id": app_id, "name": name}

    def bind_liveware_app(self, app_id: str, upstream: str) -> str:
        result = self._run_cli(
            [self._binary, "tunnel", "bind", app_id, upstream]
        )
        if result.returncode:
            detail = (result.stderr or result.stdout or "unknown error").strip()
            raise PublicationError(f"liveware tunnel bind failed: {detail}")
        output = f"{result.stdout or ''}\n{result.stderr or ''}"
        domain = self._DOMAIN.search(output)
        if domain:
            return f"https://{domain.group(1)}"
        for url in self._URL.findall(output):
            if not url.startswith(("http://127.0.0.1", "http://localhost")):
                return url
        raise PublicationError("liveware tunnel bind returned no public URL")

    def list_clawchat_apps(self) -> list[dict[str, Any]]:
        payload = self._tool_payload(
            self._invoke_tool("clawchat_list_apps", {}),
            "clawchat_list_apps",
        )
        items = payload.get("apps")
        if not isinstance(items, list):
            raise PublicationError("clawchat_list_apps returned no app list")
        return [dict(item) for item in items if isinstance(item, Mapping)]

    def register_clawchat_app(
        self, name: str, app_id: str, url: str
    ) -> None:
        self._tool_payload(
            self._invoke_tool(
                "clawchat_register_app",
                {"name": name, "appId": app_id, "url": url},
            ),
            "clawchat_register_app",
        )


class LivewarePublication:
    """Own login, app identity, binding, and ClawChat registration repair."""

    def __init__(self, adapter: PublicationAdapter) -> None:
        self._adapter = adapter

    def ensure(self) -> PublicationResult:
        try:
            apps = self._adapter.list_liveware_apps()
        except LivewareAuthenticationRequired:
            self._adapter.login_liveware()
            apps = self._adapter.list_liveware_apps()

        app = next(
            (item for item in apps if str(item.get("name") or "") == APP_NAME),
            None,
        )
        if app is None:
            app = self._adapter.create_liveware_app(APP_NAME)
        app_id = str(app.get("app_id") or app.get("appId") or "").strip()
        if not app_id:
            raise PublicationError("Liveware ClawPet app has no app id")

        url = self._adapter.bind_liveware_app(app_id, LOCAL_UPSTREAM)
        registered = self._adapter.list_clawchat_apps()
        if not any(
            str(item.get("app_id") or item.get("appId") or "") == app_id
            and str(item.get("name") or "") == APP_NAME
            and str(item.get("url") or "") == url
            for item in registered
        ):
            self._adapter.register_clawchat_app(APP_NAME, app_id, url)

        return PublicationResult(name=APP_NAME, app_id=app_id, url=url)


__all__ = [
    "HermesLivewareAdapter",
    "LivewareAuthenticationRequired",
    "LivewarePublication",
    "PublicationError",
    "PublicationResult",
]
