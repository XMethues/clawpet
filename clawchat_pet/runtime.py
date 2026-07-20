"""Authoritative in-process runtime for clawchat-pet.

The runtime owns the durable product state.  HTTP and Hermes hooks are adapters
around this object; neither adapter owns persistence or domain decisions.
"""
from __future__ import annotations

import copy
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .activity import ActivityInterpreter
from .pets import DEFAULT_PET_ID, PetModule
from .presentation import PetPresentation
from .simulator import POLICY_BY_STRATEGY_ID, apply_policy, default_save, settle_time


class ClawchatPetRuntime:
    """Own one save, one lock, and the product's public operations."""

    def __init__(
        self,
        runtime_dir: Path,
        *,
        pet_catalog: Iterable[Mapping[str, Any]] | None = None,
        pet_provider=None,
        clock: Callable[[], float] = time.time,
        presentation: PetPresentation | None = None,
    ) -> None:
        self.runtime_dir = Path(runtime_dir)
        self.save_file = self.runtime_dir / "save.json"
        self._clock = clock
        self._lock = threading.RLock()
        self._activity = ActivityInterpreter(clock=clock)
        self._pet_presentation = presentation or PetPresentation()
        self._pets = PetModule(catalog=pet_catalog, provider=pet_provider)
        with self._lock:
            if not self.save_file.exists():
                self._write(self._new_save())

    def _new_save(self) -> dict[str, Any]:
        now = float(self._clock())
        cultivation = default_save(now)
        cultivation["voice"]["ts"] = now
        cultivation["event_log"][0]["ts"] = now
        cultivation["internal"]["last_tick_ts"] = now
        return {
            "version": 1,
            "cultivation": cultivation,
            "pet": {"current": DEFAULT_PET_ID, "personalities": {}},
            "presentation": self._pet_presentation.new_selection(),
        }

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self.save_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"cannot read runtime save: {self.save_file}") from exc
        if not isinstance(data, dict):
            raise RuntimeError(f"runtime save must contain an object: {self.save_file}")
        return data

    def _write(self, data: Mapping[str, Any]) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.save_file.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporary, self.save_file)

    def _current_pet(self, save: Mapping[str, Any]) -> dict[str, Any]:
        return self._pets.current(save.get("pet") or {})

    def _personality(self, save: Mapping[str, Any], slug: str) -> dict[str, Any]:
        return self._pets.personality(save.get("pet") or {}, slug)

    def presentation(self) -> dict[str, Any]:
        with self._lock:
            save = self._read()
            if settle_time(save["cultivation"], self._clock()):
                self._write(save)
            return self._presentation(save)

    def _presentation(self, save: Mapping[str, Any]) -> dict[str, Any]:
        selection = save["presentation"]
        pet = self._current_pet(save)
        return self._pet_presentation.project(
            selection,
            save["cultivation"],
            self._activity.state(),
            pet,
            self._personality(save, str(pet["slug"])),
        )

    def handle_activity(self, event: Mapping[str, Any]) -> str:
        with self._lock:
            save = self._read()
            settled = settle_time(save["cultivation"], self._clock())
            status = self._activity.handle(
                event,
                save["cultivation"],
                lambda: self._write(save),
            )
            if status == "duplicate" and settled:
                self._write(save)
            return status

    def activity_state(self) -> dict[str, Any]:
        with self._lock:
            return self._activity.state()

    def pet_asset(self, slug: str) -> Path:
        with self._lock:
            return self._pets.sprite_path(slug)

    @staticmethod
    def _required_text(command: Mapping[str, Any], key: str) -> str:
        value = command.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must be a non-empty string")
        return value.strip()

    def command(self, command: Mapping[str, Any]) -> dict[str, Any]:
        """Apply one explicit product command and return the new presentation."""
        if not isinstance(command, Mapping):
            raise ValueError("command must be an object")
        command_type = self._required_text(command, "type")
        with self._lock:
            save = self._read()
            settle_time(save["cultivation"], self._clock())
            selection = save["presentation"]
            if self._pet_presentation.apply_command(
                selection, command_type, command
            ):
                pass
            elif command_type == "select_pet":
                self._pets.select(
                    save["pet"], self._required_text(command, "pet_id")
                )
            elif command_type == "configure_personality":
                self._pets.configure_personality(
                    save["pet"],
                    self._required_text(command, "pet_id"),
                    command.get("profile"),
                )
            elif command_type == "set_neutral_personality":
                self._pets.set_neutral_personality(
                    save["pet"], self._required_text(command, "pet_id")
                )
            elif command_type == "reset_personality":
                self._pets.reset_personality(
                    save["pet"], self._required_text(command, "pet_id")
                )
            elif command_type == "select_strategy":
                strategy_id = self._required_text(command, "strategy_id")
                try:
                    policy = POLICY_BY_STRATEGY_ID[strategy_id]
                except KeyError:
                    raise ValueError(f"unknown strategy: {strategy_id}") from None
                apply_policy(
                    save["cultivation"], policy, source="command", now=self._clock()
                )
            else:
                raise ValueError(f"unsupported command type: {command_type}")
            self._write(save)
            return self._presentation(save)

    def catalog(self) -> dict[str, Any]:
        with self._lock:
            save = self._read()
            if settle_time(save["cultivation"], self._clock()):
                self._write(save)
            selection = save["presentation"]
            presentation_catalog = self._pet_presentation.catalog(selection)
            return {
                "active": {
                    "scene_id": str(selection["scene_id"]),
                    "skin_id": str(selection["skin_id"]),
                    "pet_id": str(save["pet"]["current"]),
                },
                **presentation_catalog,
                "pets": [
                    {
                        **copy.deepcopy(item),
                        "personality_state": self._pets.personality(
                            save["pet"], str(item["slug"])
                        )["state"],
                        "prompt_personality": self._pets.personality(
                            save["pet"], str(item["slug"])
                        )["state"] == "undecided",
                    }
                    for item in self._pets.catalog().values()
                ],
            }
