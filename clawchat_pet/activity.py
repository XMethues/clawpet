"""Interpret raw Hermes callbacks into transient activity and shared growth."""
from __future__ import annotations

import copy
import json
import math
import time
import uuid
from collections.abc import Callable, Mapping
from typing import Any

from .growth import GrowthEvent, SharedGrowth


CALLBACK_NAMES = {
    "pre_tool_call",
    "post_tool_call",
    "pre_approval_request",
    "post_approval_response",
    "pre_llm_call",
    "on_session_end",
    "subagent_start",
    "subagent_stop",
}
CAPABILITY_ID_BY_TOOL = {
    "terminal": "command-execution",
    "process": "command-execution",
    "read_file": "file-inspection",
    "search_files": "file-inspection",
    "write_file": "file-editing",
    "patch": "file-editing",
    "todo": "mission-planning",
    "web_search": "remote-research",
    "web_extract": "remote-research",
    "browser_navigate": "browser-operation",
    "browser_snapshot": "browser-operation",
    "browser_click": "browser-operation",
    "browser_type": "browser-operation",
    "browser_scroll": "browser-operation",
    "browser_vision": "visual-observation",
    "vision_analyze": "visual-observation",
    "image_generate": "image-creation",
    "execute_code": "code-simulation",
    "delegate_task": "delegation",
    "session_search": "history-retrieval",
    "cronjob": "scheduled-watch",
    "skill_view": "skill-learning",
    "skill_manage": "skill-learning",
    "memory": "memory-keeping",
}
TRANSIENT_EVENT_LIMIT = 256


class ActivityValidationError(ValueError):
    pass


def _tool_outcome(result: Any) -> str:
    data = result
    if isinstance(result, str):
        try:
            data = json.loads(result)
        except (TypeError, ValueError):
            text = result.strip().lower()
            if text.startswith(("error:", "exception:", "traceback")):
                return "failure"
            return "unknown"
    if not isinstance(data, Mapping):
        return "unknown"
    if data.get("ok") is False or data.get("success") is False:
        return "failure"
    if data.get("exit_code") not in (None, 0):
        return "failure"
    if data.get("error") not in (None, "", False):
        return "failure"
    if (
        data.get("ok") is True
        or data.get("success") is True
        or data.get("exit_code") == 0
    ):
        return "success"
    return "unknown"


class ActivityInterpreter:
    """Own raw-callback correlation and transaction-local growth intake."""

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
            "pending_tool_ids": {},
            "pending_approval_ids": [],
            "pending_turn_ids": [],
            "pending_subagent_ids": [],
            "active_tools": [],
            "recent_transient_event_ids": [],
        }

    @staticmethod
    def _provided(kwargs: Mapping[str, Any], names: tuple[str, ...]) -> str:
        for name in names:
            value = kwargs.get(name)
            if value not in (None, ""):
                return str(value)
        return ""

    def _start_id(
        self,
        kwargs: Mapping[str, Any],
        names: tuple[str, ...],
        pending: list[str],
    ) -> str:
        provided = self._provided(kwargs, names)
        if provided:
            return provided
        generated = uuid.uuid4().hex
        pending.append(generated)
        return generated

    def _finish_id(
        self,
        kwargs: Mapping[str, Any],
        names: tuple[str, ...],
        pending: list[str],
    ) -> str:
        provided = self._provided(kwargs, names)
        if provided:
            return provided
        return pending.pop(0) if pending else uuid.uuid4().hex

    def _event(
        self,
        callback_name: str,
        raw_kwargs: Mapping[str, Any],
        activity: dict[str, Any],
    ) -> dict[str, Any]:
        if callback_name not in CALLBACK_NAMES:
            raise ActivityValidationError(
                f"unsupported Hermes callback: {callback_name}"
            )
        if not isinstance(raw_kwargs, Mapping):
            raise ActivityValidationError("Hermes callback kwargs must be an object")
        kwargs = dict(raw_kwargs)
        kind = ""
        payload: dict[str, Any]

        if callback_name in {"pre_tool_call", "post_tool_call"}:
            tool_name = str(
                kwargs.get("tool_name") or kwargs.get("function_name") or ""
            ).strip()
            if not tool_name:
                raise ActivityValidationError(
                    f"{callback_name} requires a tool name"
                )
            capability_id = CAPABILITY_ID_BY_TOOL.get(
                tool_name, "unclassified-work"
            )
            pending = activity["pending_tool_ids"].setdefault(tool_name, [])
            names = ("tool_call_id", "call_id", "activity_id", "id")
            if callback_name == "pre_tool_call":
                activity_id = self._start_id(kwargs, names, pending)
                activity["active_tools"].append(
                    (activity_id, capability_id)
                )
                kind = "tool_started"
                payload = {
                    "activity_id": activity_id,
                    "capability_id": capability_id,
                }
            else:
                activity_id = self._finish_id(kwargs, names, pending)
                activity["active_tools"] = [
                    item
                    for item in activity["active_tools"]
                    if item[0] != activity_id
                ]
                kind = "tool_completed"
                payload = {
                    "activity_id": activity_id,
                    "capability_id": capability_id,
                    "outcome": _tool_outcome(kwargs.get("result")),
                }
        elif callback_name == "pre_approval_request":
            activity_id = self._start_id(
                kwargs,
                ("approval_id", "request_id", "activity_id", "id"),
                activity["pending_approval_ids"],
            )
            tool_activity_id = self._provided(
                kwargs, ("tool_activity_id", "tool_call_id", "call_id")
            )
            if not tool_activity_id and activity["active_tools"]:
                tool_activity_id = activity["active_tools"][-1][0]
            kind = "approval_requested"
            payload = {
                "activity_id": activity_id,
                "mode": (
                    "smart"
                    if str(kwargs.get("surface") or "cli").lower() == "smart"
                    else "human"
                ),
                "tool_activity_id": tool_activity_id,
            }
        elif callback_name == "post_approval_response":
            activity_id = self._finish_id(
                kwargs,
                ("approval_id", "request_id", "activity_id", "id"),
                activity["pending_approval_ids"],
            )
            decision = str(kwargs.get("choice") or "unknown").strip().lower()
            if decision in {"deny", "smart_deny"}:
                decision = "denied"
            elif decision in {"once", "session", "always", "smart_approve"}:
                decision = "approved"
            kind = "approval_resolved"
            payload = {
                "activity_id": activity_id,
                "decision": decision,
                "tool_activity_id": self._provided(
                    kwargs, ("tool_activity_id", "tool_call_id", "call_id")
                ),
            }
        elif callback_name == "pre_llm_call":
            activity_id = self._start_id(
                kwargs,
                ("session_id", "turn_id", "activity_id", "id"),
                activity["pending_turn_ids"],
            )
            kind, payload = "turn_started", {"activity_id": activity_id}
        elif callback_name == "on_session_end":
            activity_id = self._finish_id(
                kwargs,
                ("session_id", "turn_id", "activity_id", "id"),
                activity["pending_turn_ids"],
            )
            kind = "turn_ended"
            payload = {
                "activity_id": activity_id,
                "outcome": (
                    "interrupted"
                    if kwargs.get("interrupted")
                    else str(kwargs.get("outcome") or "completed")
                ),
            }
        elif callback_name == "subagent_start":
            activity_id = self._start_id(
                kwargs,
                ("subagent_id", "agent_id", "activity_id", "id"),
                activity["pending_subagent_ids"],
            )
            kind, payload = "subagent_started", {"activity_id": activity_id}
        else:
            activity_id = self._finish_id(
                kwargs,
                ("subagent_id", "agent_id", "activity_id", "id"),
                activity["pending_subagent_ids"],
            )
            kind = "subagent_stopped"
            payload = {
                "activity_id": activity_id,
                "outcome": str(kwargs.get("outcome") or "completed"),
            }

        occurred_at = kwargs.get("occurred_at", self._clock())
        event_id = kwargs.get("event_id") or f"{callback_name}:{activity_id}"
        return self._validate({
            "event_id": event_id,
            "occurred_at": occurred_at,
            "kind": kind,
            "payload": payload,
        })

    @staticmethod
    def _validate(event: Mapping[str, Any]) -> dict[str, Any]:
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip():
            raise ActivityValidationError("event_id must be a non-empty string")
        occurred_at = event.get("occurred_at")
        if (
            not isinstance(occurred_at, (int, float))
            or isinstance(occurred_at, bool)
            or not math.isfinite(float(occurred_at))
        ):
            raise ActivityValidationError("occurred_at must be a finite number")
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            raise ActivityValidationError("payload must be an object")
        return {
            "event_id": event_id.strip(),
            "occurred_at": float(occurred_at),
            "kind": str(event.get("kind") or ""),
            "payload": dict(payload),
        }

    def handle(
        self,
        callback_name: str,
        raw_kwargs: Mapping[str, Any],
        growth: SharedGrowth,
        persist: Callable[[], None],
    ) -> str:
        """Correlate raw callback, persist growth, then confirm transient state."""
        activity = copy.deepcopy(self._activity)
        event = self._event(callback_name, raw_kwargs, activity)
        payload = event["payload"]
        kind = event["kind"]
        activity_id = str(payload["activity_id"])
        growth_event: GrowthEvent | None = None

        if kind == "tool_started":
            capability_id = str(payload["capability_id"])
            activity["tools"][activity_id] = {
                "capability_id": capability_id,
                "started_at": event["occurred_at"],
            }
            growth_event = GrowthEvent(
                event_id=event["event_id"],
                occurred_at=event["occurred_at"],
                kind="work_started",
                capability_id=capability_id,
            )
        elif kind == "tool_completed":
            outcome = str(payload["outcome"])
            capability_id = str(payload["capability_id"])
            activity["tools"].pop(activity_id, None)
            if activity_id in activity["blocked_tools"]:
                activity["blocked_tools"].discard(activity_id)
                outcome = "unknown"
            activity["recent_result"] = {
                "outcome": outcome,
                "capability_id": capability_id,
                "expires_at": self._clock() + 3.0,
            }
            growth_event = GrowthEvent(
                event_id=event["event_id"],
                occurred_at=event["occurred_at"],
                kind={
                    "success": "work_succeeded",
                    "failure": "work_failed",
                }.get(outcome, "work_result_unknown"),
                capability_id=capability_id,
            )
        elif kind == "approval_requested":
            activity["approvals"][activity_id] = {
                "mode": payload["mode"],
                "started_at": event["occurred_at"],
                "tool_activity_id": str(payload.get("tool_activity_id") or ""),
            }
        elif kind == "approval_resolved":
            approval = activity["approvals"].pop(activity_id, None) or {}
            tool_activity_id = str(
                payload.get("tool_activity_id")
                or approval.get("tool_activity_id")
                or ""
            )
            if tool_activity_id and payload.get("decision") in {
                "denied",
                "rejected",
                "timeout",
                "timed_out",
                "cancelled",
                "canceled",
                "blocked",
            }:
                activity["blocked_tools"].add(tool_activity_id)
        elif kind == "turn_started":
            activity["turns"][activity_id] = {
                "started_at": event["occurred_at"]
            }
        elif kind == "turn_ended":
            activity["turns"].pop(activity_id, None)
        elif kind == "subagent_started":
            activity["subagents"][activity_id] = {
                "started_at": event["occurred_at"]
            }
        elif kind == "subagent_stopped":
            activity["subagents"].pop(activity_id, None)

        if growth_event is not None:
            status = growth.apply(growth_event)
            if growth.dirty:
                persist()
            if status == "duplicate":
                return status
        else:
            recent_ids = self._activity["recent_transient_event_ids"]
            if event["event_id"] in recent_ids:
                return "duplicate"
            staged_ids = activity["recent_transient_event_ids"]
            staged_ids.append(event["event_id"])
            if len(staged_ids) > TRANSIENT_EVENT_LIMIT:
                del staged_ids[:-TRANSIENT_EVENT_LIMIT]

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
        current_capability_id = ""
        if tools:
            current_capability_id = str(
                tools[next(reversed(tools))]["capability_id"]
            )
        elif recent:
            current_capability_id = str(recent.get("capability_id") or "")
        return {
            "state": state,
            "reason": reason,
            "ts": self._clock(),
            "current_capability_id": current_capability_id,
            "in_flight": {
                "tools": len(tools),
                "approvals": len(approvals),
                "turns": len(self._activity["turns"]),
                "subagents": len(self._activity["subagents"]),
            },
        }
