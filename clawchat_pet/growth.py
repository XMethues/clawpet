"""Scene-neutral shared growth behind one in-process interface."""
from __future__ import annotations

import copy
import math
import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping


__all__ = ["GrowthEvent", "GrowthFact", "GrowthSnapshot", "SharedGrowth"]


_STATE_VERSION = 1
_STRATEGY_IDS = ("balanced", "advance", "stabilize", "learn", "recover")
_IDLE_DAY_SECONDS = 86_400.0
_FACT_LIMIT = 140
_ASSET_CAPABILITIES = {
    "command-execution",
    "file-inspection",
    "file-editing",
    "mission-planning",
    "remote-research",
    "browser-operation",
    "image-creation",
    "scheduled-watch",
    "skill-learning",
}
_DIMENSION_IDS = {
    "primary",
    "stability",
    "risk",
    "insight",
    "fortune",
    "strain",
}
_STATE_KEYS = {
    "version",
    "stage_index",
    "dimensions",
    "strategy_id",
    "capabilities",
    "assets",
    "recent_facts",
    "processed_event_ids",
    "last_active_at",
    "idle_applied_stage",
    "last_failure_open",
}


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _valid_capabilities(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    for capability_id, item in value.items():
        if (
            not isinstance(capability_id, str)
            or not capability_id
            or not isinstance(item, dict)
            or set(item) != {"level", "xp", "xp_next"}
            or not isinstance(item["level"], int)
            or isinstance(item["level"], bool)
            or item["level"] < 1
            or not _is_number(item["xp"])
            or not _is_number(item["xp_next"])
            or float(item["xp"]) < 0
            or float(item["xp_next"]) <= 0
        ):
            return False
    return True


def _valid_assets(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    for capability_id, item in value.items():
        if (
            not isinstance(capability_id, str)
            or not capability_id
            or not isinstance(item, dict)
            or set(item) != {"level", "tier", "xp"}
            or not isinstance(item["level"], int)
            or isinstance(item["level"], bool)
            or item["level"] < 1
            or item["tier"] not in {"basic", "enhanced", "core"}
            or not _is_number(item["xp"])
            or float(item["xp"]) < 0
        ):
            return False
    return True


def _valid_facts(value: Any) -> bool:
    if not isinstance(value, list) or len(value) > _FACT_LIMIT:
        return False
    for fact in value:
        if (
            not isinstance(fact, dict)
            or set(fact) != {"occurred_at", "kind", "capability_id", "data"}
            or not _is_number(fact["occurred_at"])
            or not isinstance(fact["kind"], str)
            or not fact["kind"]
            or not isinstance(fact["capability_id"], str)
            or not isinstance(fact["data"], dict)
            or not all(isinstance(key, str) for key in fact["data"])
            or not all(
                item is None
                or isinstance(item, (str, int, float, bool))
                and (not isinstance(item, float) or math.isfinite(item))
                for item in fact["data"].values()
            )
        ):
            return False
    return True


_STRATEGY_PROFILES: Mapping[str, Mapping[str, float]] = {
    "balanced": {
        "primary": 1.0,
        "insight": 1.0,
        "failure_risk": 0.75,
        "failure_strain": 0.80,
        "idle_decay": 0.50,
        "idle_recovery": 1.35,
        "success_recovery": 1.0,
        "risk_recovery": 1.0,
    },
    "advance": {
        "primary": 1.55,
        "insight": 0.90,
        "failure_risk": 1.60,
        "failure_strain": 1.45,
        "idle_decay": 1.70,
        "idle_recovery": 0.75,
        "success_recovery": 0.85,
        "risk_recovery": 0.80,
    },
    "stabilize": {
        "primary": 0.95,
        "insight": 1.05,
        "failure_risk": 0.55,
        "failure_strain": 0.95,
        "idle_decay": 0.85,
        "idle_recovery": 1.0,
        "success_recovery": 1.0,
        "risk_recovery": 1.55,
    },
    "learn": {
        "primary": 0.90,
        "insight": 1.55,
        "failure_risk": 1.0,
        "failure_strain": 1.0,
        "idle_decay": 1.15,
        "idle_recovery": 1.0,
        "success_recovery": 1.0,
        "risk_recovery": 1.0,
    },
    "recover": {
        "primary": 0.90,
        "insight": 1.0,
        "failure_risk": 0.85,
        "failure_strain": 0.70,
        "idle_decay": 0.85,
        "idle_recovery": 1.80,
        "success_recovery": 1.60,
        "risk_recovery": 1.15,
    },
}


def _stage_path() -> tuple[dict[str, float | str], ...]:
    stages: list[dict[str, float | str]] = []
    for index, primary_max in enumerate(
        (30, 60, 100, 150, 220, 310, 430, 580, 760)
    ):
        stages.append(
            {
                "kind": "minor",
                "primary_max": float(primary_max),
                "risk_max": 50.0 if index < 8 else 35.0,
                "strain_max": 80.0 if index < 8 else 70.0,
                "stability_min": 0.0 if index < 8 else 3.0,
                "insight_min": 0.0 if index < 8 else 3.0,
            }
        )
    for base, stability_min, insight_min in (
        (1050, 5, 6),
        (1800, 9, 10),
        (3000, 14, 15),
    ):
        for index in range(4):
            stages.append(
                {
                    "kind": "minor" if index < 3 else "major",
                    "primary_max": float(int(base * (1 + index * 0.55))),
                    "risk_max": float(max(20, 38 - index * 3)),
                    "strain_max": float(72 - index * 3),
                    "stability_min": float(stability_min + index * 2),
                    "insight_min": float(insight_min + index * 2),
                }
            )
    stages.extend(
        (
            {
                "kind": "gate",
                "primary_max": 5200.0,
                "risk_max": 20.0,
                "strain_max": 55.0,
                "stability_min": 24.0,
                "insight_min": 26.0,
            },
            {
                "kind": "trial",
                "primary_max": 6200.0,
                "risk_max": 18.0,
                "strain_max": 50.0,
                "stability_min": 28.0,
                "insight_min": 30.0,
            },
            {
                "kind": "trial",
                "primary_max": 7400.0,
                "risk_max": 15.0,
                "strain_max": 45.0,
                "stability_min": 32.0,
                "insight_min": 34.0,
            },
        )
    )
    for index in range(4):
        stages.append(
            {
                "kind": "minor" if index < 3 else "major",
                "primary_max": float(int(8800 * (1 + index * 0.50))),
                "risk_max": float(max(8, 12 - index)),
                "strain_max": float(42 - index * 2),
                "stability_min": float(36 + index * 3),
                "insight_min": float(38 + index * 3),
            }
        )
    return tuple(stages)


_STAGE_PATH = _stage_path()


@dataclass(frozen=True)
class GrowthEvent:
    """One normalized durable event produced from Hermes activity."""

    event_id: str
    occurred_at: float
    kind: str
    capability_id: str = ""


@dataclass(frozen=True)
class GrowthDimension:
    id: str
    value: float
    maximum: float | None = None


@dataclass(frozen=True)
class GrowthFact:
    occurred_at: float
    kind: str
    capability_id: str
    data: Mapping[str, Any]


@dataclass(frozen=True)
class GrowthStage:
    index: int
    total: int
    kind: str
    ready: bool
    requirements: Mapping[str, float]


@dataclass(frozen=True)
class GrowthStrategy:
    id: str
    choices: tuple[str, ...]


@dataclass(frozen=True)
class GrowthDormancy:
    days: float
    stage: int
    phase: str


@dataclass(frozen=True)
class GrowthCapability:
    id: str
    level: int
    xp: float
    xp_next: float


@dataclass(frozen=True)
class GrowthAsset:
    id: str
    level: int
    tier: str
    xp: float


@dataclass(frozen=True)
class GrowthSnapshot:
    stage: GrowthStage
    dimensions: Mapping[str, GrowthDimension]
    strategy: GrowthStrategy
    dormancy: GrowthDormancy
    capabilities: Mapping[str, GrowthCapability]
    assets: Mapping[str, GrowthAsset]
    recent_facts: tuple[GrowthFact, ...]


class SharedGrowth:
    """Own shared growth state, evolution, time settlement, and serialization."""

    def __init__(self, state: Mapping[str, Any], *, clock: Callable[[], float]):
        self._state = copy.deepcopy(dict(state))
        self._clock = clock
        self._dirty = False
        if self._state.get("version") != _STATE_VERSION:
            raise ValueError("unsupported shared growth state")
        self._validate_current_state()

    def _validate_current_state(self) -> None:
        state = self._state
        valid = (
            set(state) == _STATE_KEYS
            and isinstance(state.get("stage_index"), int)
            and not isinstance(state.get("stage_index"), bool)
            and 0 <= int(state.get("stage_index", -1)) < len(_STAGE_PATH)
            and isinstance(state.get("dimensions"), dict)
            and set(state.get("dimensions", {})) == _DIMENSION_IDS
            and all(
                _is_number(value)
                for value in state.get("dimensions", {}).values()
            )
            and state.get("strategy_id") in _STRATEGY_IDS
            and _valid_capabilities(state.get("capabilities"))
            and _valid_assets(state.get("assets"))
            and _valid_facts(state.get("recent_facts"))
            and isinstance(state.get("processed_event_ids"), list)
            and all(
                isinstance(event_id, str) and bool(event_id)
                for event_id in state.get("processed_event_ids", [])
            )
            and len(state.get("processed_event_ids", []))
            == len(set(state.get("processed_event_ids", [])))
            and _is_number(state.get("last_active_at"))
            and isinstance(state.get("idle_applied_stage"), int)
            and not isinstance(state.get("idle_applied_stage"), bool)
            and 0 <= int(state.get("idle_applied_stage", -1)) <= 5
            and isinstance(state.get("last_failure_open"), bool)
        )
        if not valid:
            raise ValueError("invalid shared growth state")

    @classmethod
    def fresh(cls, *, clock: Callable[[], float] = time.time) -> "SharedGrowth":
        now = float(clock())
        return cls(
            {
                "version": _STATE_VERSION,
                "stage_index": 0,
                "dimensions": {
                    "primary": 0.0,
                    "stability": 1.0,
                    "risk": 0.0,
                    "insight": 1.0,
                    "fortune": 3.0,
                    "strain": 0.0,
                },
                "strategy_id": "balanced",
                "capabilities": {},
                "assets": {},
                "recent_facts": [
                    {
                        "occurred_at": now,
                        "kind": "born",
                        "capability_id": "",
                        "data": {},
                    }
                ],
                "processed_event_ids": [],
                "last_active_at": now,
                "idle_applied_stage": 0,
                "last_failure_open": False,
            },
            clock=clock,
        )

    @classmethod
    def load(
        cls,
        serialized: Mapping[str, Any],
        *,
        clock: Callable[[], float] = time.time,
    ) -> "SharedGrowth":
        return cls(serialized, clock=clock)

    @property
    def dirty(self) -> bool:
        return self._dirty

    def serialize(self) -> dict[str, Any]:
        return copy.deepcopy(self._state)

    def _profile(self) -> Mapping[str, float]:
        return _STRATEGY_PROFILES[str(self._state["strategy_id"])]

    def _mark_active(self) -> None:
        self._state["last_active_at"] = float(self._clock())
        self._state["idle_applied_stage"] = 0

    @staticmethod
    def _idle_stage(days: float) -> tuple[int, str]:
        if days >= 5:
            return 5, "regression_check"
        if days >= 4:
            return 4, "heavy_decay"
        if days >= 3:
            return 3, "stability_loss"
        if days >= 2:
            return 2, "risk_rise"
        if days >= 1:
            return 1, "minor_decay"
        return 0, "active"

    def _record_fact(
        self,
        kind: str,
        *,
        occurred_at: float,
        capability_id: str = "",
        data: Mapping[str, Any] | None = None,
    ) -> None:
        facts = self._state["recent_facts"]
        facts.append(
            {
                "occurred_at": float(occurred_at),
                "kind": kind,
                "capability_id": capability_id,
                "data": copy.deepcopy(dict(data or {})),
            }
        )
        if len(facts) > _FACT_LIMIT:
            del facts[:-_FACT_LIMIT]

    def _settle_time(self) -> None:
        now = float(self._clock())
        last_active = float(self._state["last_active_at"])
        days = max(0.0, (now - last_active) / _IDLE_DAY_SECONDS)
        due, _phase = self._idle_stage(days)
        applied = int(self._state["idle_applied_stage"])
        if due <= applied:
            return
        dimensions = self._state["dimensions"]
        profile = self._profile()
        decay = profile["idle_decay"]
        recovery = profile["idle_recovery"]
        for stage in range(applied + 1, due + 1):
            fact_kind = "idle_decay"
            fact_data = {"stage": stage}
            if stage == 1:
                dimensions["primary"] = float(dimensions["primary"]) * max(
                    0.0, 1.0 - 0.04 * decay
                )
                dimensions["strain"] = max(
                    0.0, float(dimensions["strain"]) - 8.0 * recovery
                )
            elif stage == 2:
                dimensions["primary"] = float(dimensions["primary"]) * max(
                    0.0, 1.0 - 0.07 * decay
                )
                dimensions["risk"] = float(dimensions["risk"]) + 1.5 * decay
                dimensions["stability"] = max(
                    0.0, float(dimensions["stability"]) - 0.15 * decay
                )
            elif stage == 3:
                dimensions["primary"] = float(dimensions["primary"]) * max(
                    0.0, 1.0 - 0.12 * decay
                )
                dimensions["stability"] = max(
                    0.0, float(dimensions["stability"]) - 0.35 * decay
                )
                dimensions["risk"] = float(dimensions["risk"]) + 2.0 * decay
            elif stage == 4:
                dimensions["primary"] = float(dimensions["primary"]) * max(
                    0.0, 1.0 - 0.22 * decay
                )
                dimensions["insight"] = max(
                    0.0,
                    float(dimensions["insight"])
                    - 0.25 * decay / max(0.1, profile["insight"]),
                )
                dimensions["risk"] = float(dimensions["risk"]) + 3.0 * decay
            else:
                dimensions["primary"] = float(dimensions["primary"]) * max(
                    0.0, 1.0 - 0.30 * decay
                )
                dimensions["risk"] = float(dimensions["risk"]) + 4.0 * decay
                stage_index = int(self._state["stage_index"])
                rule = _STAGE_PATH[stage_index]
                if (
                    stage_index > 0
                    and rule["kind"] != "trial"
                    and float(dimensions["risk"]) > float(rule["risk_max"])
                    and float(dimensions["stability"])
                    < float(rule["stability_min"])
                ):
                    self._state["stage_index"] = stage_index - 1
                    previous_rule = _STAGE_PATH[stage_index - 1]
                    dimensions["risk"] = max(
                        0.0, float(dimensions["risk"]) - 20.0
                    )
                    dimensions["primary"] = min(
                        float(dimensions["primary"]),
                        float(previous_rule["primary_max"]) * 0.30,
                    )
                    fact_kind = "stage_regressed"
                    fact_data.update({
                        "from_index": stage_index,
                        "to_index": stage_index - 1,
                    })
            self._record_fact(fact_kind, occurred_at=now, data=fact_data)
        self._normalize_dimensions()
        self._state["idle_applied_stage"] = due
        self._dirty = True

    def _normalize_dimensions(self) -> None:
        dimensions = self._state["dimensions"]
        stage = _STAGE_PATH[int(self._state["stage_index"])]
        maximums = {
            "primary": float(stage["primary_max"]),
            "stability": 999.0,
            "risk": 200.0,
            "insight": 999.0,
            "fortune": 999.0,
            "strain": 100.0,
        }
        for key, maximum in maximums.items():
            dimensions[key] = round(
                max(0.0, min(maximum, float(dimensions[key]))), 2
            )

    def _bump_capability(
        self, capability_id: str, xp: float, *, occurred_at: float
    ) -> None:
        item = self._state["capabilities"].setdefault(
            capability_id, {"level": 1, "xp": 0.0, "xp_next": 20.0}
        )
        item["xp"] = float(item["xp"]) + xp
        while float(item["xp"]) >= float(item["xp_next"]):
            item["xp"] = float(item["xp"]) - float(item["xp_next"])
            item["level"] = int(item["level"]) + 1
            item["xp_next"] = round(float(item["xp_next"]) * 1.5, 1)
            self._record_fact(
                "capability_advanced",
                occurred_at=occurred_at,
                capability_id=capability_id,
                data={"level": int(item["level"])},
            )
        item["xp"] = round(float(item["xp"]), 2)

    def _bump_asset(
        self, capability_id: str, xp: float, *, occurred_at: float
    ) -> None:
        if capability_id not in _ASSET_CAPABILITIES:
            return
        item = self._state["assets"].setdefault(
            capability_id,
            {"level": 1, "tier": "basic", "xp": 0.0},
        )
        item["xp"] = float(item["xp"]) + xp
        needed = 30 + int(item["level"]) * 15
        if float(item["xp"]) >= needed:
            item["xp"] = float(item["xp"]) - needed
            item["level"] = int(item["level"]) + 1
            if int(item["level"]) >= 6:
                item["tier"] = "core"
            elif int(item["level"]) >= 3:
                item["tier"] = "enhanced"
            self._record_fact(
                "asset_advanced",
                occurred_at=occurred_at,
                capability_id=capability_id,
                data={"level": int(item["level"]), "tier": item["tier"]},
            )
        item["xp"] = round(float(item["xp"]), 2)

    def _stage_is_ready(self) -> bool:
        rule = _STAGE_PATH[int(self._state["stage_index"])]
        dimensions = self._state["dimensions"]
        return (
            float(dimensions["primary"]) >= float(rule["primary_max"])
            and float(dimensions["risk"]) <= float(rule["risk_max"])
            and float(dimensions["strain"]) <= float(rule["strain_max"])
            and float(dimensions["stability"])
            >= float(rule["stability_min"])
            and float(dimensions["insight"]) >= float(rule["insight_min"])
        )

    def _advance_stage(self, trigger_kind: str, *, occurred_at: float) -> None:
        current_index = int(self._state["stage_index"])
        if current_index >= len(_STAGE_PATH) - 1 or not self._stage_is_ready():
            return
        current_rule = _STAGE_PATH[current_index]
        if current_rule["kind"] == "trial" and trigger_kind != "work_succeeded":
            return
        next_index = current_index + 1
        dimensions = self._state["dimensions"]
        self._state["stage_index"] = next_index
        dimensions["primary"] = 0.0
        if current_rule["kind"] == "trial":
            dimensions["stability"] = float(dimensions["stability"]) + 2.0
            dimensions["insight"] = float(dimensions["insight"]) + 1.2
        else:
            stability_gain = 0.5 if current_rule["kind"] == "minor" else 1.5
            dimensions["stability"] = (
                float(dimensions["stability"]) + stability_gain
            )
        self._record_fact(
            "stage_advanced",
            occurred_at=occurred_at,
            data={"from_index": current_index, "to_index": next_index},
        )

    def apply(self, event: GrowthEvent) -> str:
        event_id = str(event.event_id or "").strip()
        if not event_id:
            raise ValueError("growth event_id must be a non-empty string")
        if not _is_number(event.occurred_at):
            raise ValueError("growth occurred_at must be finite")
        if event.kind not in {
            "work_started",
            "work_succeeded",
            "work_failed",
            "work_result_unknown",
        }:
            raise ValueError(f"unsupported growth event: {event.kind}")
        capability_id = str(event.capability_id or "").strip()
        if not capability_id:
            raise ValueError("growth work event requires capability_id")
        self._settle_time()
        processed = self._state["processed_event_ids"]
        if event_id in processed:
            return "duplicate"
        dimensions = self._state["dimensions"]
        stage = _STAGE_PATH[int(self._state["stage_index"])]
        profile = self._profile()
        if event.kind == "work_started":
            dimensions["strain"] = float(dimensions["strain"]) + 0.35
            self._bump_capability(
                capability_id, 0.4, occurred_at=event.occurred_at
            )
            self._record_fact(
                event.kind,
                occurred_at=event.occurred_at,
                capability_id=capability_id,
            )
        elif event.kind == "work_succeeded":
            primary_gain = 2.4 * profile["primary"]
            dimensions["primary"] = min(
                float(stage["primary_max"]),
                float(dimensions["primary"]) + primary_gain,
            )
            dimensions["strain"] = max(
                0.0,
                float(dimensions["strain"])
                - 0.35 * profile["success_recovery"],
            )
            dimensions["fortune"] = float(dimensions["fortune"]) + 0.05
            if self._state["last_failure_open"]:
                dimensions["stability"] = float(dimensions["stability"]) + 1.0
                dimensions["risk"] = max(
                    0.0,
                    float(dimensions["risk"])
                    - 3.0 * profile["risk_recovery"],
                )
                self._record_fact(
                    "work_recovered", occurred_at=event.occurred_at
                )
            self._bump_capability(
                capability_id, 2.4, occurred_at=event.occurred_at
            )
            self._bump_asset(capability_id, 1.7, occurred_at=event.occurred_at)
            self._record_fact(
                event.kind,
                occurred_at=event.occurred_at,
                capability_id=capability_id,
                data={"primary_gain": round(primary_gain, 2)},
            )
            self._state["last_failure_open"] = False
        elif event.kind == "work_failed":
            dimensions["risk"] = (
                float(dimensions["risk"]) + 4.5 * profile["failure_risk"]
            )
            dimensions["strain"] = (
                float(dimensions["strain"])
                + 1.4 * profile["failure_strain"]
            )
            self._record_fact(
                event.kind,
                occurred_at=event.occurred_at,
                capability_id=capability_id,
            )
            self._state["last_failure_open"] = True
        self._normalize_dimensions()
        self._advance_stage(event.kind, occurred_at=event.occurred_at)
        self._normalize_dimensions()
        processed.append(event_id)
        if event.kind != "work_result_unknown":
            self._mark_active()
        self._dirty = True
        return "accepted"

    def select_strategy(self, strategy_id: str) -> None:
        self._settle_time()
        strategy_id = str(strategy_id or "").strip()
        if strategy_id not in _STRATEGY_IDS:
            raise ValueError(f"unknown strategy: {strategy_id}")
        self._state["strategy_id"] = strategy_id
        self._record_fact(
            "strategy_selected",
            occurred_at=self._clock(),
            data={"strategy_id": strategy_id},
        )
        self._dirty = True

    def observe(self) -> GrowthSnapshot:
        self._settle_time()
        raw_dimensions = self._state["dimensions"]
        stage_index = int(self._state["stage_index"])
        stage_rule = _STAGE_PATH[stage_index]
        maximums = {
            "primary": float(stage_rule["primary_max"]),
            "risk": 100.0,
            "strain": 100.0,
        }
        dimensions = MappingProxyType({
            dimension_id: GrowthDimension(
                id=dimension_id,
                value=float(value),
                maximum=maximums.get(dimension_id),
            )
            for dimension_id, value in raw_dimensions.items()
        })
        facts = tuple(
            GrowthFact(
                occurred_at=float(item["occurred_at"]),
                kind=str(item["kind"]),
                capability_id=str(item.get("capability_id") or ""),
                data=MappingProxyType(
                    copy.deepcopy(dict(item.get("data") or {}))
                ),
            )
            for item in self._state["recent_facts"]
        )
        capabilities = MappingProxyType({
            capability_id: GrowthCapability(
                id=capability_id,
                level=int(item["level"]),
                xp=float(item["xp"]),
                xp_next=float(item["xp_next"]),
            )
            for capability_id, item in self._state["capabilities"].items()
        })
        assets = MappingProxyType({
            capability_id: GrowthAsset(
                id=capability_id,
                level=int(item["level"]),
                tier=str(item["tier"]),
                xp=float(item["xp"]),
            )
            for capability_id, item in self._state["assets"].items()
        })
        requirements = MappingProxyType({
            "primary": float(stage_rule["primary_max"]),
            "risk": float(stage_rule["risk_max"]),
            "strain": float(stage_rule["strain_max"]),
            "stability": float(stage_rule["stability_min"]),
            "insight": float(stage_rule["insight_min"]),
        })
        ready = (
            dimensions["primary"].value >= requirements["primary"]
            and dimensions["risk"].value <= requirements["risk"]
            and dimensions["strain"].value <= requirements["strain"]
            and dimensions["stability"].value >= requirements["stability"]
            and dimensions["insight"].value >= requirements["insight"]
            and stage_rule["kind"] != "cap"
        )
        idle_days = max(
            0.0,
            (float(self._clock()) - float(self._state["last_active_at"]))
            / _IDLE_DAY_SECONDS,
        )
        idle_stage, idle_phase = self._idle_stage(idle_days)
        return GrowthSnapshot(
            stage=GrowthStage(
                index=stage_index,
                total=len(_STAGE_PATH),
                kind=str(stage_rule["kind"]),
                ready=ready,
                requirements=requirements,
            ),
            dimensions=dimensions,
            strategy=GrowthStrategy(
                id=str(self._state["strategy_id"]), choices=_STRATEGY_IDS
            ),
            dormancy=GrowthDormancy(
                days=round(idle_days, 3), stage=idle_stage, phase=idle_phase
            ),
            capabilities=capabilities,
            assets=assets,
            recent_facts=facts,
        )
