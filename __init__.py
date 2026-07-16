"""clawchat-pet Hermes plugin entrypoint."""
from __future__ import annotations

import atexit
import json
import sys
import urllib.request
from pathlib import Path

_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

_AUTOSTART_REGISTERED = False
_LIVEWARE_ATEXIT_REGISTERED = False
_SKILL_REGISTERED = False


def _skill_description(skill_path: Path) -> str:
    """Read the frontmatter description from a plugin SKILL.md."""
    fallback = "银月道场 cultivation pet gameplay and liveware presence."
    try:
        text = skill_path.read_text(encoding="utf-8")
    except Exception:
        return fallback
    in_frontmatter = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "---":
            if not in_frontmatter:
                in_frontmatter = True
                continue
            break
        if in_frontmatter and stripped.startswith("description:"):
            value = stripped.split(":", 1)[1].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'\"', "'"}:
                value = value[1:-1]
            return value or fallback
    return fallback


def _register_skill(ctx) -> None:
    """Register the bundled skill as an explicit plugin skill only."""
    global _SKILL_REGISTERED
    if _SKILL_REGISTERED:
        return
    register_skill = getattr(ctx, "register_skill", None)
    if not callable(register_skill):
        return
    skill_path = _PLUGIN_DIR / "skills" / "clawchat-pet" / "SKILL.md"
    if not skill_path.exists():
        return
    register_skill(
        "clawchat-pet",
        skill_path,
        description=_skill_description(skill_path),
    )
    _SKILL_REGISTERED = True


def _server_already_running() -> bool:
    """Return True when the configured local clawchat-pet API is healthy.

    The plugin autostarts its embedded server by default, but a standalone
    server may already be serving the configured HOST/PORT. Reuse it instead of
    raising an address-in-use error during Hermes plugin registration.
    """
    try:
        from clawchat_pet import server as _server

        url = f"http://{_server.HOST}:{_server.PORT}/healthz"
        with urllib.request.urlopen(url, timeout=0.2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return bool(data.get("ok") is True and data.get("service") == "clawchat-pet")
    except Exception:
        return False


def _ensure_server_running() -> bool:
    """Autostart the embedded server if no healthy one is already available.

    Returns True when this call started an in-process server, and False when an
    existing healthy server was reused. Repeated register() calls in one Hermes
    process should not stack duplicate atexit handlers.
    """
    global _AUTOSTART_REGISTERED

    if _server_already_running():
        return False

    from clawchat_pet import server

    server.start_background()
    if not _AUTOSTART_REGISTERED:
        atexit.register(server.stop_background)
        _AUTOSTART_REGISTERED = True
    return True


def _ensure_liveware_running() -> bool:
    """Start the Liveware tunnel agent and register plugin-owned cleanup once."""
    global _LIVEWARE_ATEXIT_REGISTERED

    from clawchat_pet import liveware

    started = liveware.ensure_running()
    if not _LIVEWARE_ATEXIT_REGISTERED:
        atexit.register(liveware.stop)
        _LIVEWARE_ATEXIT_REGISTERED = True
    return started


def register(ctx) -> None:
    from clawchat_pet.hooks import register_hooks

    register_hooks(ctx)
    _register_skill(ctx)

    # The plugin owns both parts of its runtime lifecycle: start the local PET
    # API first, then start the Liveware data-plane that exposes that API.
    _ensure_server_running()
    _ensure_liveware_running()
