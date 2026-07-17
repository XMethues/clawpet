"""Hermes hooks that deliver normalized activity to the owned pet server."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any

HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
LOG_FILE = HERMES_HOME / "clawchat-pet" / "plugin.log"
SERVER_URL = os.environ.get("CLAWCHAT_PET_SERVER_URL", "http://127.0.0.1:54321")
POST_TIMEOUT = float(os.environ.get("CLAWCHAT_PET_HOOK_TIMEOUT", "0.2"))
_SEQ = 0


def _log(msg: str) -> None:
    global _SEQ
    _SEQ += 1
    line = f"[clawchat-pet #{_SEQ} {time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, file=sys.stderr, flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        pass


def _post_event(payload: dict[str, Any], server_url: str) -> bool:
    try:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            server_url.rstrip("/") + "/api/v1/events",
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=POST_TIMEOUT) as response:
            return 200 <= int(response.status) < 300
    except Exception:
        return False


def _emit(server_url: str, kind: str, payload: dict[str, Any]) -> None:
    envelope = {
        "schema_version": 1,
        "event_id": uuid.uuid4().hex,
        "occurred_at": time.time(),
        "kind": kind,
        "payload": payload,
    }
    if not _post_event(envelope, server_url):
        _log(f"{kind} dropped: server unavailable")


def _identifier(kwargs: dict[str, Any], *names: str, fallback: str) -> str:
    for name in names:
        value = kwargs.get(name)
        if value not in (None, ""):
            return str(value)
    return fallback


def _tool_outcome(result: Any) -> str:
    data = result
    if isinstance(result, str):
        try:
            data = json.loads(result)
        except Exception:
            text = result.strip().lower()
            if text.startswith(("error:", "exception:", "traceback")):
                return "failure"
            return "unknown"
    if not isinstance(data, dict):
        return "unknown"
    if data.get("ok") is False or data.get("success") is False:
        return "failure"
    if data.get("exit_code") not in (None, 0):
        return "failure"
    if data.get("error") not in (None, "", False):
        return "failure"
    if data.get("ok") is True or data.get("success") is True or data.get("exit_code") == 0:
        return "success"
    return "unknown"


def register_hooks(ctx, server_url: str | None = None) -> None:
    endpoint = server_url or SERVER_URL
    pending_tool_ids: dict[str, list[str]] = {}
    pending_approval_ids: list[str] = []
    pending_turn_ids: list[str] = []
    pending_subagent_ids: list[str] = []
    active_tools: list[tuple[str, str]] = []

    def start_id(kwargs: dict[str, Any], names: tuple[str, ...], pending: list[str]) -> str:
        provided = next((
            kwargs.get(name) for name in names if kwargs.get(name) not in (None, "")
        ), None)
        if provided is not None:
            return str(provided)
        generated = uuid.uuid4().hex
        pending.append(generated)
        return generated

    def finish_id(kwargs: dict[str, Any], names: tuple[str, ...], pending: list[str]) -> str:
        provided = next((
            kwargs.get(name) for name in names if kwargs.get(name) not in (None, "")
        ), None)
        if provided is not None:
            return str(provided)
        return pending.pop(0) if pending else uuid.uuid4().hex

    def pre_tool_call(**kwargs):
        tool = str(kwargs.get("tool_name") or kwargs.get("function_name") or "").strip()
        if tool:
            provided = next((kwargs.get(name) for name in (
                "tool_call_id", "call_id", "activity_id", "id"
            ) if kwargs.get(name) not in (None, "")), None)
            activity_id = str(provided) if provided is not None else uuid.uuid4().hex
            if provided is None:
                pending_tool_ids.setdefault(tool, []).append(activity_id)
            active_tools.append((activity_id, tool))
            _emit(endpoint, "tool_started", {"activity_id": activity_id, "tool_name": tool})

    def post_tool_call(**kwargs):
        tool = str(kwargs.get("function_name") or kwargs.get("tool_name") or "").strip()
        if tool:
            provided = next((kwargs.get(name) for name in (
                "tool_call_id", "call_id", "activity_id", "id"
            ) if kwargs.get(name) not in (None, "")), None)
            pending = pending_tool_ids.get(tool, [])
            activity_id = str(provided) if provided is not None else (
                pending.pop(0) if pending else uuid.uuid4().hex
            )
            active_tools[:] = [item for item in active_tools if item[0] != activity_id]
            _emit(endpoint, "tool_completed", {
                "activity_id": activity_id,
                "tool_name": tool,
                "outcome": _tool_outcome(kwargs.get("result")),
            })

    def pre_approval_request(**kwargs):
        activity_id = start_id(
            kwargs, ("approval_id", "request_id", "activity_id", "id"),
            pending_approval_ids,
        )
        raw_mode = str(kwargs.get("approval_mode") or kwargs.get("mode") or "human").lower()
        mode = "smart" if raw_mode in {"smart", "auto", "automatic"} or kwargs.get("is_smart_mode") else "human"
        tool_activity_id = _identifier(
            kwargs, "tool_activity_id", "tool_call_id", "call_id", fallback=""
        )
        if not tool_activity_id and active_tools:
            tool_activity_id = active_tools[-1][0]
        payload = {"activity_id": activity_id, "mode": mode}
        if tool_activity_id:
            payload["tool_activity_id"] = tool_activity_id
        _emit(endpoint, "approval_requested", payload)

    def post_approval_response(**kwargs):
        activity_id = finish_id(
            kwargs, ("approval_id", "request_id", "activity_id", "id"),
            pending_approval_ids,
        )
        decision = str(kwargs.get("decision") or kwargs.get("status") or "unknown")
        payload = {"activity_id": activity_id, "decision": decision}
        tool_activity_id = _identifier(
            kwargs, "tool_activity_id", "tool_call_id", "call_id", fallback=""
        )
        if tool_activity_id:
            payload["tool_activity_id"] = tool_activity_id
        _emit(endpoint, "approval_resolved", payload)

    def pre_llm_call(**kwargs):
        activity_id = start_id(
            kwargs, ("session_id", "turn_id", "activity_id", "id"),
            pending_turn_ids,
        )
        _emit(endpoint, "turn_started", {"activity_id": activity_id})

    def on_session_end(**kwargs):
        activity_id = finish_id(
            kwargs, ("session_id", "turn_id", "activity_id", "id"),
            pending_turn_ids,
        )
        outcome = "interrupted" if kwargs.get("interrupted") else str(kwargs.get("outcome") or "completed")
        _emit(endpoint, "turn_ended", {"activity_id": activity_id, "outcome": outcome})

    def subagent_start(**kwargs):
        activity_id = start_id(
            kwargs, ("subagent_id", "agent_id", "activity_id", "id"),
            pending_subagent_ids,
        )
        _emit(endpoint, "subagent_started", {"activity_id": activity_id})

    def subagent_stop(**kwargs):
        activity_id = finish_id(
            kwargs, ("subagent_id", "agent_id", "activity_id", "id"),
            pending_subagent_ids,
        )
        _emit(endpoint, "subagent_stopped", {
            "activity_id": activity_id,
            "outcome": str(kwargs.get("outcome") or "completed"),
        })

    callbacks = {
        "pre_tool_call": pre_tool_call,
        "post_tool_call": post_tool_call,
        "pre_approval_request": pre_approval_request,
        "post_approval_response": post_approval_response,
        "pre_llm_call": pre_llm_call,
        "on_session_end": on_session_end,
        "subagent_start": subagent_start,
        "subagent_stop": subagent_stop,
    }
    _log("registering hooks...")
    for name, callback in callbacks.items():
        try:
            ctx.register_hook(name, callback)
            _log(f"✓ {name} registered")
        except Exception as exc:
            _log(f"✗ {name}: {exc}")
