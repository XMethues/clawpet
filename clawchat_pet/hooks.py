"""Thin Hermes hook adapter for the in-process clawchat-pet runtime."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .runtime import ClawchatPetRuntime


HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
LOG_FILE = HERMES_HOME / "clawchat-pet" / "plugin.log"
_SEQ = 0


def _log(message: str) -> None:
    global _SEQ
    _SEQ += 1
    line = f"[clawchat-pet #{_SEQ} {time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    print(line, file=sys.stderr, flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        pass


def _forward(
    runtime: "ClawchatPetRuntime",
    callback_name: str,
    raw_kwargs: dict[str, Any],
) -> None:
    try:
        runtime.handle_activity(callback_name, raw_kwargs)
    except Exception as exc:
        _log(f"{callback_name} dropped: {exc}")


def register_hooks(ctx, runtime: "ClawchatPetRuntime") -> None:
    """Register adapters that forward each Hermes callback without interpretation."""

    def adapter(callback_name: str):
        def callback(**kwargs):
            _forward(runtime, callback_name, kwargs)

        return callback

    callback_names = (
        "pre_tool_call",
        "post_tool_call",
        "pre_approval_request",
        "post_approval_response",
        "pre_llm_call",
        "on_session_end",
        "subagent_start",
        "subagent_stop",
    )
    _log("registering hooks...")
    for name in callback_names:
        try:
            ctx.register_hook(name, adapter(name))
            _log(f"✓ {name} registered")
        except Exception as exc:
            _log(f"✗ {name}: {exc}")
