"""Versioned Hermes activity intake and aggregate transient activity state."""
from __future__ import annotations

import copy
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from .simulator import (
    apply_cultivation_event,
    apply_policy,
    default_save,
    policy_state,
    public_state,
)

SCHEMA_VERSION = 1
PERSONALITY_EVENTS = {"idle", "review", "run", "wave", "failed", "waiting", "unknown", "subagent"}
DEFAULT_PET = {
    "slug": "yinyue-2", "displayName": "宠物", "description": "",
    "source": "petdex", "assetKind": "sprite", "cached": False,
    "spriteUrl": "/api/v1/pets/yinyue-2/sprite.png",
    "cellWidth": 192, "cellHeight": 208,
}
EVENT_KINDS = {
    "tool_started", "tool_completed", "approval_requested", "approval_resolved",
    "turn_started", "turn_ended", "subagent_started", "subagent_stopped",
}


class EventValidationError(ValueError):
    pass


def _merge_defaults(base: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    for key, value in base.items():
        if key not in data:
            data[key] = copy.deepcopy(value)
        elif isinstance(value, dict) and isinstance(data[key], dict):
            _merge_defaults(value, data[key])
    return data


class ActivityRuntime:
    """Own persistent cultivation and transient activity for one server."""

    def __init__(self, cultivation_file: Path, pet_catalog=None, pet_provider=None) -> None:
        self.cultivation_file = Path(cultivation_file)
        self.legacy_cultivation_file = (
            self.cultivation_file.parent.parent / "cultivation" / "yinyue.json"
        )
        self.current_pet_file = self.cultivation_file.parent / "current_pet.json"
        self.legacy_current_pet_file = (
            self.cultivation_file.parent.parent / "yinyue-dao" / "current_pet.json"
        )
        self.personalities_file = self.cultivation_file.parent / "personalities.json"
        self._pet_catalog = {
            str(item["slug"]): copy.deepcopy(item) for item in (pet_catalog or [])
        } if pet_catalog is not None else None
        self._pet_provider = pet_provider
        self._lock = threading.RLock()
        self._activity: dict[str, Any] = {
            "tools": {}, "approvals": {}, "turns": {}, "subagents": {},
            "recent_result": None, "blocked_tools": set(),
        }

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.cultivation_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            try:
                data = json.loads(self.legacy_cultivation_file.read_text(encoding="utf-8"))
            except FileNotFoundError:
                data = default_save()
        if not isinstance(data, dict):
            raise ValueError("cultivation save must be a JSON object")
        return _merge_defaults(default_save(), data)

    def _write(self, save: dict[str, Any]) -> None:
        self.cultivation_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.cultivation_file.with_suffix(self.cultivation_file.suffix + ".tmp")
        tmp.write_text(json.dumps(save, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.cultivation_file)

    @staticmethod
    def _validate(envelope: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(envelope, dict):
            raise EventValidationError("JSON object required")
        if envelope.get("schema_version") != SCHEMA_VERSION:
            raise EventValidationError(f"schema_version must be {SCHEMA_VERSION}")
        event_id = envelope.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip():
            raise EventValidationError("event_id must be a non-empty string")
        occurred_at = envelope.get("occurred_at")
        if not isinstance(occurred_at, (int, float)) or isinstance(occurred_at, bool):
            raise EventValidationError("occurred_at must be a number")
        kind = envelope.get("kind")
        if kind not in EVENT_KINDS:
            raise EventValidationError("unsupported event kind")
        payload = envelope.get("payload")
        if not isinstance(payload, dict):
            raise EventValidationError("payload must be an object")
        return {
            "event_id": event_id.strip(), "occurred_at": float(occurred_at),
            "kind": kind, "payload": dict(payload),
        }

    def ingest(self, envelope: dict[str, Any]) -> str:
        event = self._validate(envelope)
        with self._lock:
            save = self._load()
            processed = save.setdefault("internal", {}).setdefault("processed_event_ids", [])
            if event["event_id"] in processed:
                return "duplicate"

            activity = copy.deepcopy(self._activity)
            payload = event["payload"]
            kind = event["kind"]
            activity_id = str(payload.get("activity_id") or "").strip()
            if not activity_id:
                raise EventValidationError(f"{kind} requires activity_id")
            if kind in {"tool_started", "tool_completed"}:
                tool_name = str(payload.get("tool_name") or "").strip()
                if not tool_name:
                    raise EventValidationError(f"{kind} requires tool_name")
            if kind == "tool_started":
                activity["tools"][activity_id] = {
                    "tool_name": tool_name, "started_at": event["occurred_at"],
                }
                apply_cultivation_event(save, {
                    "state": "run", "tool": tool_name, "ts": event["occurred_at"],
                    "event_id": event["event_id"],
                })
            elif kind == "tool_completed":
                outcome = payload.get("outcome")
                if outcome not in {"success", "failure", "unknown"}:
                    raise EventValidationError(
                        "tool_completed outcome must be success, failure, or unknown"
                    )
                activity["tools"].pop(activity_id, None)
                if activity_id in activity["blocked_tools"]:
                    activity["blocked_tools"].discard(activity_id)
                    outcome = "unknown"
                activity["recent_result"] = {
                    "outcome": outcome, "tool_name": tool_name,
                    "expires_at": time.monotonic() + 3.0,
                }
                legacy_state = {"success": "wave", "failure": "failed"}.get(outcome)
                if legacy_state:
                    apply_cultivation_event(save, {
                        "state": legacy_state, "tool": tool_name,
                        "success": outcome == "success",
                        "ts": event["occurred_at"], "event_id": event["event_id"],
                    })
                else:
                    processed.append(event["event_id"])
            elif kind == "approval_requested":
                mode = payload.get("mode")
                if mode not in {"human", "smart"}:
                    raise EventValidationError("approval mode must be human or smart")
                activity["approvals"][activity_id] = {
                    "mode": mode, "started_at": event["occurred_at"],
                    "tool_activity_id": str(
                        payload.get("tool_activity_id") or ""
                    ).strip(),
                }
                processed.append(event["event_id"])
            elif kind == "approval_resolved":
                approval = activity["approvals"].pop(activity_id, None) or {}
                decision = str(payload.get("decision") or "").strip().lower()
                tool_activity_id = str(
                    payload.get("tool_activity_id")
                    or approval.get("tool_activity_id")
                    or ""
                ).strip()
                if tool_activity_id and decision in {
                    "denied", "rejected", "timeout", "timed_out",
                    "cancelled", "canceled", "blocked",
                }:
                    activity["blocked_tools"].add(tool_activity_id)
                processed.append(event["event_id"])
            elif kind == "turn_started":
                activity["turns"][activity_id] = {"started_at": event["occurred_at"]}
                processed.append(event["event_id"])
            elif kind == "turn_ended":
                activity["turns"].pop(activity_id, None)
                processed.append(event["event_id"])
            elif kind == "subagent_started":
                activity["subagents"][activity_id] = {"started_at": event["occurred_at"]}
                processed.append(event["event_id"])
            elif kind == "subagent_stopped":
                activity["subagents"].pop(activity_id, None)
                processed.append(event["event_id"])
            self._write(save)
            self._activity = activity
            return "accepted"

    def activity_state(self) -> dict[str, Any]:
        with self._lock:
            tools = self._activity["tools"]
            recent = self._activity["recent_result"]
            if recent and time.monotonic() >= recent["expires_at"]:
                recent = None
                self._activity["recent_result"] = None
            approvals = self._activity["approvals"]
            human_waiting = any(item["mode"] == "human" for item in approvals.values())
            smart_waiting = any(item["mode"] == "smart" for item in approvals.values())
            if human_waiting:
                state, reason = "waiting", "human-approval"
            elif tools:
                state, reason = "run", "direct-tool"
            elif self._activity["subagents"]:
                state, reason = "subagent", "delegated-work"
            elif recent:
                state = {"success": "wave", "failure": "failed"}.get(
                    recent["outcome"], "unknown"
                )
                reason = "recent-result"
            elif self._activity["turns"] or smart_waiting:
                state, reason = "review", "inference"
            else:
                state, reason = "idle", "no activity"
            return {
                "state": state,
                "reason": reason,
                "ts": time.time(),
                "in_flight": {
                    "tools": len(tools),
                    "approvals": len(self._activity["approvals"]),
                    "turns": len(self._activity["turns"]),
                    "subagents": len(self._activity["subagents"]),
                },
            }

    def cultivation_state(self) -> dict[str, Any]:
        with self._lock:
            state = public_state(self._load())
            pet = self.current_pet()
            state = self._replace_legacy_identity(state, pet["displayName"])
            state.setdefault("profile", {}).update({
                "name": pet["displayName"], "pet_id": pet["slug"],
            })
            state.setdefault("voice", {})["speaker"] = pet["displayName"]
            return state

    def get_policy(self) -> dict[str, Any]:
        with self._lock:
            return policy_state(self._load())

    def set_policy(self, name: str, source: str = "plugin") -> dict[str, Any]:
        with self._lock:
            save = self._load()
            policy = apply_policy(save, name, source)
            self._write(save)
            return policy

    def event_log(self, limit: int = 50) -> dict[str, Any]:
        with self._lock:
            logs = public_state(self._load()).get("event_log", [])[-limit:]
            return {"events": logs, "count": len(logs)}

    def _catalog(self) -> dict[str, dict[str, Any]]:
        if self._pet_catalog is not None:
            return self._pet_catalog
        try:
            petdex = self._petdex()
            catalog = {
                str(pet.slug): self._pet_dict(pet)
                for pet in petdex.list_pets(force=False)
            }
        except Exception:
            catalog = {}
        catalog.setdefault("yinyue-2", copy.deepcopy(DEFAULT_PET))
        return catalog

    def _petdex(self):
        if self._pet_provider is not None:
            return self._pet_provider
        from .services import petdex

        return petdex

    @staticmethod
    def _pet_dict(pet) -> dict[str, Any]:
        if isinstance(pet, dict):
            return copy.deepcopy(pet)
        return copy.deepcopy(pet.to_dict())

    def list_pets(self) -> list[dict[str, Any]]:
        return list(self._catalog().values())

    def current_pet(self) -> dict[str, Any]:
        if self._pet_catalog is None:
            try:
                return self._pet_dict(self._petdex().current_pet())
            except Exception:
                if self._pet_provider is not None:
                    raise
                return copy.deepcopy(DEFAULT_PET)
        slug = "yinyue-2"
        try:
            source = self.current_pet_file if self.current_pet_file.exists() else self.legacy_current_pet_file
            data = json.loads(source.read_text(encoding="utf-8"))
            slug = str(data.get("slug") or slug)
        except (FileNotFoundError, ValueError, TypeError):
            pass
        catalog = self._catalog()
        if slug in catalog:
            return copy.deepcopy(catalog[slug])
        if "yinyue-2" in catalog:
            return copy.deepcopy(catalog["yinyue-2"])
        raise KeyError("Petdex default pet yinyue-2 is unavailable")

    def select_pet(self, slug: str) -> dict[str, Any]:
        if self._pet_catalog is None:
            return self._pet_dict(self._petdex().set_current_pet(slug))
        catalog = self._catalog()
        if slug not in catalog:
            raise KeyError(f"unknown Petdex pet: {slug}")
        self.current_pet_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.current_pet_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"slug": slug}, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.current_pet_file)
        return copy.deepcopy(catalog[slug])

    def _load_personalities(self) -> dict[str, Any]:
        try:
            data = json.loads(self.personalities_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        if not isinstance(data, dict):
            raise ValueError("personalities must be a JSON object")
        return data

    def _write_personalities(self, data: dict[str, Any]) -> None:
        self.personalities_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.personalities_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.personalities_file)

    def personality(self, slug: str) -> dict[str, Any]:
        if slug not in self._catalog():
            raise KeyError(f"unknown Petdex pet: {slug}")
        stored = self._load_personalities().get(slug)
        if not stored:
            return {"slug": slug, "state": "undecided", "profile": None}
        return {"slug": slug, **copy.deepcopy(stored)}

    def update_personality(self, slug: str, body: dict[str, Any]) -> dict[str, Any]:
        if slug not in self._catalog():
            raise KeyError(f"unknown Petdex pet: {slug}")
        if not isinstance(body, dict):
            raise EventValidationError("personality update must be an object")
        action = str(body.get("action") or "").strip()
        personalities = self._load_personalities()
        if action in {"neutral", "decline"}:
            personalities[slug] = {"state": "neutral", "profile": None}
        elif action == "reset":
            personalities.pop(slug, None)
        elif action == "configure":
            profile = body.get("profile")
            if not isinstance(profile, dict):
                raise EventValidationError("profile must be an object")
            allowed = {"style", "lines"}
            if set(profile) - allowed:
                raise EventValidationError("profile contains unsupported fields")
            style = profile.get("style")
            lines = profile.get("lines")
            if not isinstance(style, str) or not style.strip() or len(style) > 200:
                raise EventValidationError("style must be 1-200 characters")
            if not isinstance(lines, dict) or not lines or set(lines) - PERSONALITY_EVENTS:
                raise EventValidationError("lines contain unsupported event groups")
            normalized_lines: dict[str, list[str]] = {}
            for event, values in lines.items():
                if not isinstance(values, list) or not 1 <= len(values) <= 20:
                    raise EventValidationError("each line group must contain 1-20 lines")
                if any(not isinstance(line, str) or not line.strip() or len(line) > 200 for line in values):
                    raise EventValidationError("personality lines must be 1-200 characters")
                normalized_lines[event] = [line.strip() for line in values]
            personalities[slug] = {
                "state": "configured",
                "profile": {"style": style.strip(), "lines": normalized_lines},
            }
        else:
            raise EventValidationError("action must be configure, neutral, decline, or reset")
        self._write_personalities(personalities)
        return self.personality(slug)

    def pet_selection(self, slug: str) -> dict[str, Any]:
        pet = self.select_pet(slug)
        personality = self.personality(slug)
        return {
            "pet": pet,
            "personality_state": personality["state"],
            "prompt_personality": personality["state"] == "undecided",
        }

    @classmethod
    def _replace_legacy_identity(cls, value: Any, display_name: str) -> Any:
        if isinstance(value, str):
            return value.replace("银月", display_name)
        if isinstance(value, list):
            return [cls._replace_legacy_identity(item, display_name) for item in value]
        if isinstance(value, dict):
            return {
                key: cls._replace_legacy_identity(item, display_name)
                for key, item in value.items()
            }
        return value

    def voice_state(self) -> dict[str, Any]:
        state = self.cultivation_state()
        voice = copy.deepcopy(state.get("voice") or {})
        if not voice:
            voice = {
                "speaker": self.current_pet()["displayName"],
                "mood": "calm", "text": "我在。", "ts": time.time(), "event": "idle",
            }
        pet = self.current_pet()
        personality = self.personality(pet["slug"])
        profile = personality.get("profile") or {}
        lines = profile.get("lines") or {}
        activity_event = self.activity_state()["state"]
        event_lines = lines.get(activity_event) or lines.get(str(voice.get("event") or "idle"))
        if event_lines:
            voice["text"] = event_lines[0]
            voice["event"] = activity_event
        voice["speaker"] = pet["displayName"]
        return voice
