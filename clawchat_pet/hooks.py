"""Hermes lifecycle hooks for 银月道场.

These hooks are intentionally tiny: they observe Hermes activity and deliver
small events to the local clawchat-pet HTTP server. There is no JSONL fallback;
failed delivery is logged only.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
STATE_FILE = HERMES_HOME / "pet_state.json"
LOG_FILE = HERMES_HOME / "clawchat-pet" / "plugin.log"
SERVER_URL = os.environ.get("CLAWCHAT_PET_SERVER_URL", "http://127.0.0.1:54321")
POST_TIMEOUT = float(os.environ.get("CLAWCHAT_PET_HOOK_TIMEOUT", "0.2"))
_SEQ = 0


def _log(msg: str) -> None:
    global _SEQ
    _SEQ += 1
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[clawchat-pet #{_SEQ} {ts}] {msg}"
    print(line, file=sys.stderr, flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _post_event(payload: dict[str, Any]) -> bool:
    try:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        req = urllib.request.Request(
            SERVER_URL.rstrip("/") + "/api/v1/events",
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=POST_TIMEOUT) as resp:
            return 200 <= int(resp.status) < 300
    except Exception:
        return False


def _write_state(state: str, reason: str, **extra: Any) -> None:
    payload = {"state": state, "reason": reason, "ts": time.time(), "event_id": f"{os.getpid()}:{time.time_ns()}", **extra}
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, STATE_FILE)
        if _post_event(payload):
            _log(f"→ {state:8s} ({reason}) via http")
        else:
            _log(f"→ {state:8s} ({reason}) dropped: server unavailable")
    except Exception as exc:
        _log(f"state write failed: {exc}")


def _looks_like_error(result: object) -> bool:
    """Return True only for concrete tool failures.

    Hermes tool results are often JSON strings that include an ``"error": null``
    field.  The old substring heuristic treated any string containing
    ``"error"`` as failure, so successful terminal calls became ``failed`` and
    polluted the cultivation simulator.  Prefer structured signals; fall back
    only to unmistakable traceback/error text.
    """
    def from_dict(data: dict[str, Any]) -> bool:
        if data.get("ok") is False or data.get("success") is False:
            return True
        if data.get("exit_code") not in (None, 0):
            return True
        err = data.get("error")
        if err not in (None, "", False):
            return True
        return False

    if isinstance(result, dict):
        return from_dict(result)
    if isinstance(result, str):
        text = result.strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return from_dict(parsed)
        except Exception:
            pass
        low = text.lower()
        return (
            "traceback (most recent call last)" in low
            or low.startswith("traceback")
            or low.startswith("error:")
            or low.startswith("exception:")
        )
    return False


def register_hooks(ctx) -> None:
    def pre_tool_call(**kwargs):
        tool_name = kwargs.get("tool_name", "") or ""
        if tool_name:
            _write_state("run", f"tool:{tool_name}", tool=tool_name, event="pre_tool_call")

    def post_tool_call(**kwargs):
        tool_name = kwargs.get("function_name", "") or kwargs.get("tool_name", "") or ""
        if not tool_name:
            return
        result = kwargs.get("result")
        ok = not _looks_like_error(result)
        _write_state("wave" if ok else "failed", f"tool:{tool_name}", tool=tool_name, event="post_tool_call", success=ok)

    hooks = [
        ("pre_tool_call", pre_tool_call),
        ("post_tool_call", post_tool_call),
        ("pre_llm_call", lambda **kw: _write_state("review", "thinking", event="pre_llm_call")),
        ("post_llm_call", lambda **kw: _write_state("idle", "turn-done", event="post_llm_call")),
        ("pre_approval_request", lambda **kw: _write_state("waiting", "approval", event="pre_approval_request")),
    ]
    _log("registering hooks...")
    for name, cb in hooks:
        try:
            ctx.register_hook(name, cb)
            _log(f"✓ {name} registered")
        except Exception as exc:
            _log(f"✗ {name}: {exc}")
    if not STATE_FILE.exists():
        _write_state("idle", "startup", event="startup")
