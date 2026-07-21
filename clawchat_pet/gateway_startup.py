"""Install and handle the ClawPet Gateway startup hook."""
from __future__ import annotations

import atexit
import logging
import os
import threading
from pathlib import Path
from typing import Any, Mapping


HOOK_NAME = "clawchat-pet-startup"
PLUGIN_ACTIVE_ENV = "CLAWCHAT_PET_PLUGIN_ACTIVE"
_HOOK_FILES = ("HOOK.yaml", "handler.py")
_LIVEWARE_ATEXIT_REGISTERED = False
_STARTUP_THREAD: threading.Thread | None = None
_STARTUP_LOCK = threading.Lock()
_LOGGER = logging.getLogger("clawchat-pet")


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def install_gateway_hook(
    plugin_dir: Path,
    *,
    hermes_home: Path | None = None,
) -> Path:
    """Materialize and activate the bundled hook for this Hermes process."""
    source = Path(plugin_dir) / "gateway_hooks" / HOOK_NAME
    destination = (hermes_home or _hermes_home()) / "hooks" / HOOK_NAME
    destination.mkdir(parents=True, exist_ok=True)

    for filename in _HOOK_FILES:
        source_file = source / filename
        destination_file = destination / filename
        content = source_file.read_bytes()
        try:
            unchanged = destination_file.read_bytes() == content
        except FileNotFoundError:
            unchanged = False
        if unchanged:
            continue
        temporary = destination / (
            f".{filename}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        try:
            temporary.write_bytes(content)
            temporary.replace(destination_file)
        finally:
            temporary.unlink(missing_ok=True)

    os.environ[PLUGIN_ACTIVE_ENV] = "1"
    return destination


def _register_liveware_cleanup() -> None:
    global _LIVEWARE_ATEXIT_REGISTERED
    if _LIVEWARE_ATEXIT_REGISTERED:
        return
    from . import liveware

    atexit.register(liveware.stop)
    _LIVEWARE_ATEXIT_REGISTERED = True


def _ensure_liveware_running() -> bool:
    from . import liveware

    return liveware.ensure_running()


def _run_liveware_startup() -> None:
    """Repair the complete Liveware data plane without blocking Gateway."""
    try:
        _ensure_liveware_running()
    except Exception:
        _LOGGER.exception("ClawPet Liveware agent startup failed")

    try:
        from .publication import HermesLivewareAdapter, LivewarePublication

        result = LivewarePublication(HermesLivewareAdapter()).ensure()
        _LOGGER.info(
            "ClawPet publication ready app_id=%s url=%s",
            result.app_id,
            result.url,
        )
    except Exception:
        _LOGGER.exception("ClawPet publication startup failed")
    finally:
        # Login or app repair may have made the agent usable after the first
        # attempt, so always give it one more chance.
        try:
            _ensure_liveware_running()
        except Exception:
            _LOGGER.exception("ClawPet Liveware agent restart failed")


def handle_gateway_startup(
    event_type: str,
    context: Mapping[str, Any] | None = None,
) -> bool:
    """Schedule Liveware startup once for a ``gateway:startup`` event."""
    global _STARTUP_THREAD
    if event_type != "gateway:startup":
        return False

    with _STARTUP_LOCK:
        _register_liveware_cleanup()
        if _STARTUP_THREAD is not None and _STARTUP_THREAD.is_alive():
            return False
        _STARTUP_THREAD = threading.Thread(
            target=_run_liveware_startup,
            name="clawchat-pet-liveware-startup",
            daemon=True,
        )
        _STARTUP_THREAD.start()

    platforms = list((context or {}).get("platforms") or [])
    _LOGGER.info("ClawPet Liveware startup scheduled platforms=%s", platforms)
    return True


__all__ = [
    "HOOK_NAME",
    "PLUGIN_ACTIVE_ENV",
    "handle_gateway_startup",
    "install_gateway_hook",
]
