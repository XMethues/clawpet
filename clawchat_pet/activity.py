"""Interpret Hermes lifecycle callbacks into activity and shared growth."""
from __future__ import annotations

import copy
import time
from collections.abc import Callable, Mapping
from typing import Any

from .simulator import apply_cultivation_event


SCHEMA_VERSION = 1
EVENT_KINDS = {
    "tool_started",
    "tool_completed",
    "approval_requested",
    "approval_resolved",
    "turn_started",
    "turn_ended",
    "subagent_started",
    "subagent_stopped",
}


class ActivityValidationError(ValueError):
    pass


class ActivityInterpreter:
    """Own transient Hermes activity and update caller-owned growth state."""

    def __init__(self, *, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._activity = self._empty_activity()

    @staticmethod
    def _empty_activity() -> dict[str, Any]:
        return {
            "tools": {},
            "approvals": {},
            "turns": {},
            "subagents": {},
            "recent_result": None,
            "blocked_tools": set(),
        }

    @staticmethod
    def _validate(envelope: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(envelope, Mapping):
            raise ActivityValidationError("activity event must be an object")
        if envelope.get("schema_version") != SCHEMA_VERSION:
            raise ActivityValidationError(f"schema_version must be {SCHEMA_VERSION}")
        event_id = envelope.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip():
            raise ActivityValidationError("event_id must be a non-empty string")
        occurred_at = envelope.get("occurred_at")
        if not isinstance(occurred_at, (int, float)) or isinstance(occurred_at, bool):
            raise ActivityValidationError("occurred_at must be a number")
        kind = envelope.get("kind")
        if kind not in EVENT_KINDS:
            raise ActivityValidationError("unsupported event kind")
        payload = envelope.get("payload")
        if not isinstance(payload, Mapping):
            raise ActivityValidationError("payload must be an object")
        return {
            "event_id": event_id.strip(),
            "occurred_at": float(occurred_at),
            "kind": kind,
            "payload": dict(payload),
        }

    def handle(
        self,
        envelope: Mapping[str, Any],
        cultivation: dict[str, Any],
        persist: Callable[[], None],
    ) -> str:
        """Stage activity + growth, persist growth, then commit transient state."""
        event = self._validate(envelope)
        processed = cultivation.setdefault("internal", {}).setdefault(
            "processed_event_ids", []
        )
        if event["event_id"] in processed:
            return "duplicate"

        activity = copy.deepcopy(self._activity)
        payload = event["payload"]
        kind = event["kind"]
        activity_id = str(payload.get("activity_id") or "").strip()
        if not activity_id:
            raise ActivityValidationError(f"{kind} requires activity_id")

        tool_name = ""
        if kind in {"tool_started", "tool_completed"}:
            tool_name = str(payload.get("tool_name") or "").strip()
            if not tool_name:
                raise ActivityValidationError(f"{kind} requires tool_name")

        if kind == "tool_started":
            activity["tools"][activity_id] = {
                "tool_name": tool_name,
                "started_at": event["occurred_at"],
            }
            apply_cultivation_event(cultivation, {
                "state": "run",
                "tool": tool_name,
                "ts": event["occurred_at"],
                "event_id": event["event_id"],
            }, now=self._clock())
        elif kind == "tool_completed":
            outcome = payload.get("outcome")
            if outcome not in {"success", "failure", "unknown"}:
                raise ActivityValidationError(
                    "tool_completed outcome must be success, failure, or unknown"
                )
            activity["tools"].pop(activity_id, None)
            if activity_id in activity["blocked_tools"]:
                activity["blocked_tools"].discard(activity_id)
                outcome = "unknown"
            activity["recent_result"] = {
                "outcome": outcome,
                "tool_name": tool_name,
                "expires_at": self._clock() + 3.0,
            }
            growth_state = {"success": "wave", "failure": "failed"}.get(outcome)
            if growth_state:
                apply_cultivation_event(cultivation, {
                    "state": growth_state,
                    "tool": tool_name,
                    "success": outcome == "success",
                    "ts": event["occurred_at"],
                    "event_id": event["event_id"],
                }, now=self._clock())
            else:
                processed.append(event["event_id"])
        elif kind == "approval_requested":
            mode = payload.get("mode")
            if mode not in {"human", "smart"}:
                raise ActivityValidationError("approval mode must be human or smart")
            activity["approvals"][activity_id] = {
                "mode": mode,
                "started_at": event["occurred_at"],
                "tool_activity_id": str(payload.get("tool_activity_id") or "").strip(),
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
                "denied", "rejected", "timeout", "timed_out", "cancelled",
                "canceled", "blocked",
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
            activity["subagents"][activity_id] = {
                "started_at": event["occurred_at"]
            }
            processed.append(event["event_id"])
        elif kind == "subagent_stopped":
            activity["subagents"].pop(activity_id, None)
            processed.append(event["event_id"])

        persist()
        self._activity = activity
        return "accepted"

    def state(self) -> dict[str, Any]:
        tools = self._activity["tools"]
        recent = self._activity["recent_result"]
        if recent and self._clock() >= recent["expires_at"]:
            recent = None
            self._activity["recent_result"] = None
        approvals = self._activity["approvals"]
        if any(item["mode"] == "human" for item in approvals.values()):
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
        elif self._activity["turns"] or any(
            item["mode"] == "smart" for item in approvals.values()
        ):
            state, reason = "review", "inference"
        else:
            state, reason = "idle", "no activity"
        current_tool = ""
        if tools:
            current_tool = str(tools[next(reversed(tools))]["tool_name"])
        elif recent:
            current_tool = str(recent.get("tool_name") or "")
        return {
            "state": state,
            "reason": reason,
            "ts": self._clock(),
            "current_tool": current_tool,
            "in_flight": {
                "tools": len(tools),
                "approvals": len(approvals),
                "turns": len(self._activity["turns"]),
                "subagents": len(self._activity["subagents"]),
            },
        }
