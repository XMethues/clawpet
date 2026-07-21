"""Gateway adapter for the plugin-owned ClawPet Liveware startup."""
from __future__ import annotations

import os


def handle(event_type: str, context: dict) -> None:
    # The materialized hook can outlive a disabled or removed plugin. Only the
    # plugin's successful register() call activates it for this process.
    if os.environ.get("CLAWCHAT_PET_PLUGIN_ACTIVE") != "1":
        return

    from clawchat_pet.gateway_startup import handle_gateway_startup

    handle_gateway_startup(event_type, context)
