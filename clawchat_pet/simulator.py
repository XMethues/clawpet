#!/usr/bin/env python3
"""Cultivation simulator for clawchat-pet.

The simulator turns Hermes activity into a long-lived pet/cultivation save:
- realm progression: 炼气九层 → 筑基 → 金丹 → 元婴 → 化神门槛 → 雷劫试炼 → 元神试炼 → 化神
- event-driven stats from Hermes hook events
- pet personality / voice bubble text for the liveware UI
"""
from __future__ import annotations

import copy
import json
import os
import random
import threading
import time
from pathlib import Path
from typing import Any

HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
STATE_FILE = HERMES_HOME / "pet_state.json"
DATA_DIR = HERMES_HOME / "clawchat-pet"
SAVE_DIR = DATA_DIR
SAVE_FILE = SAVE_DIR / "cultivation.json"
LEGACY_SAVE_FILE = HERMES_HOME / "cultivation" / "yinyue.json"

WINDOW_SIZE = 30
LOG_SIZE = 140
TICK_SECONDS = 1.0
_SAVE_LOCK = threading.RLock()
REVIEW_AFTER = 3.0
IDLE_AFTER = 8.0

POLICY_NAMES = ("入定", "冲关", "淬心", "悟道", "调息")
POLICY_PROFILES: dict[str, dict[str, float | str]] = {
    "入定": {
        "label": "入定", "qi_w": 1.0, "review_qi_w": 1.0, "compr_w": 1.0,
        "fail_demon_w": 0.75, "fail_fatigue_w": 0.80, "idle_decay_w": 0.50,
        "idle_fatigue_recover_w": 1.35, "wave_fatigue_recover_w": 1.0, "recovery_demon_w": 1.0,
    },
    "冲关": {
        "label": "冲关", "qi_w": 1.55, "review_qi_w": 1.10, "compr_w": 0.90,
        "fail_demon_w": 1.60, "fail_fatigue_w": 1.45, "idle_decay_w": 1.70,
        "idle_fatigue_recover_w": 0.75, "wave_fatigue_recover_w": 0.85, "recovery_demon_w": 0.80,
    },
    "淬心": {
        "label": "淬心", "qi_w": 0.95, "review_qi_w": 0.95, "compr_w": 1.05,
        "fail_demon_w": 0.55, "fail_fatigue_w": 0.95, "idle_decay_w": 0.85,
        "idle_fatigue_recover_w": 1.0, "wave_fatigue_recover_w": 1.0, "recovery_demon_w": 1.55,
    },
    "悟道": {
        "label": "悟道", "qi_w": 0.90, "review_qi_w": 0.80, "compr_w": 1.55,
        "fail_demon_w": 1.0, "fail_fatigue_w": 1.0, "idle_decay_w": 1.15,
        "idle_fatigue_recover_w": 1.0, "wave_fatigue_recover_w": 1.0, "recovery_demon_w": 1.0,
    },
    "调息": {
        "label": "调息", "qi_w": 0.90, "review_qi_w": 0.90, "compr_w": 1.0,
        "fail_demon_w": 0.85, "fail_fatigue_w": 0.70, "idle_decay_w": 0.85,
        "idle_fatigue_recover_w": 1.80, "wave_fatigue_recover_w": 1.60, "recovery_demon_w": 1.15,
    },
}
DEFAULT_POLICY = "入定"

CULT_ACTIONS = {
    "idle": "入定吐纳",
    "review": "推演天机",
    "run": "御剑历练",
    "wave": "收束因果",
    "failed": "心魔侵扰",
    "waiting": "静候法旨",
    "jump": "灵光乍现",
}

TECHNIQUE_BY_TOOL = {
    "terminal": "御剑诀",
    "process": "御剑诀",
    "read_file": "天机推演",
    "search_files": "天机推演",
    "write_file": "符箓编纂",
    "patch": "符箓编纂",
    "todo": "执事录",
    "web_search": "神识外放",
    "web_extract": "神识外放",
    "browser_navigate": "分身入世",
    "browser_snapshot": "分身入世",
    "browser_click": "分身入世",
    "browser_type": "分身入世",
    "browser_scroll": "分身入世",
    "browser_vision": "灵目观世",
    "image_generate": "幻术造化",
    "vision_analyze": "灵目观象",
    "execute_code": "内景推演",
    "delegate_task": "分神化身",
    "session_search": "追溯前尘",
    "cronjob": "分身值守",
    "skill_view": "传承参悟",
    "skill_manage": "传承参悟",
    "memory": "识海铭刻",
}

ARTIFACT_BY_TOOL = {
    "terminal": ("本命飞剑", "sword"),
    "process": ("本命飞剑", "sword"),
    "read_file": ("观天灵镜", "mirror"),
    "search_files": ("观天灵镜", "mirror"),
    "write_file": ("符笔", "brush"),
    "patch": ("符笔", "brush"),
    "todo": ("执事玉简", "tablet"),
    "web_search": ("观天盘", "astrolabe"),
    "web_extract": ("观天盘", "astrolabe"),
    "browser_navigate": ("云舟", "vessel"),
    "image_generate": ("幻月灯", "lamp"),
    "cronjob": ("值守傀儡", "puppet"),
    "skill_manage": ("传承玉匣", "manual"),
}


def _tool_label(tool: str) -> str:
    """Return a player-facing cultivation name without leaking tool internals."""
    if not tool:
        return ""
    return TECHNIQUE_BY_TOOL.get(tool, "无名术法")


def _sanitize_log_text(typ: str, text: str) -> str:
    """Translate raw tool names in old saved tool-event logs for display."""
    if typ not in {"tool_success", "tool_failed"} or "：" not in text:
        return text
    prefix, rest = text.split("：", 1)
    if "，" not in rest:
        return text
    raw_tool, suffix = rest.split("，", 1)
    if raw_tool in TECHNIQUE_BY_TOOL:
        return f"{prefix}：{_tool_label(raw_tool)}，{suffix}"
    if raw_tool.replace("_", "").isalnum() and raw_tool.isascii():
        return f"{prefix}：无名术法，{suffix}"
    return text


# Ordered realm graph. 化神 no longer hard-stops at the gate:
# 元婴圆满 -> 化神门槛 -> 雷劫试炼 -> 元神试炼 -> 化神初/中/后/圆满.
REALM_PATH: list[dict[str, Any]] = []
for i, qi in enumerate([30, 60, 100, 150, 220, 310, 430, 580, 760], start=1):
    REALM_PATH.append({
        "key": f"lianqi-{i}", "major": "炼气", "minor": i, "phase": "",
        "label": f"炼气{i}层", "max_qi": qi, "kind": "minor",
        "next": f"炼气{i + 1}层" if i < 9 else "筑基初期",
        "heart_demon_max": 50 if i < 9 else 35,
        "fatigue_max": 80 if i < 9 else 70,
        "dao_heart_min": 0 if i < 9 else 3,
        "comprehension_min": 0 if i < 9 else 3,
    })
for major, base, dh, comp in [("筑基", 1050, 5, 6), ("金丹", 1800, 9, 10), ("元婴", 3000, 14, 15)]:
    for idx, phase in enumerate(["初期", "中期", "后期", "圆满"]):
        REALM_PATH.append({
            "key": f"{major}-{idx}", "major": major, "minor": idx + 1, "phase": phase,
            "label": f"{major}{phase}", "max_qi": int(base * (1 + idx * 0.55)),
            "kind": "minor" if idx < 3 else "major",
            "next": (f"{major}{['中期','后期','圆满'][idx]}" if idx < 3 else {"筑基":"金丹初期","金丹":"元婴初期","元婴":"化神门槛"}[major]),
            "heart_demon_max": max(20, 38 - idx * 3),
            "fatigue_max": 72 - idx * 3,
            "dao_heart_min": dh + idx * 2,
            "comprehension_min": comp + idx * 2,
        })
REALM_PATH.extend([
    {
        "key": "huashen-gate", "major": "化神", "minor": 0, "phase": "门槛",
        "label": "化神门槛", "max_qi": 5200, "kind": "gate", "next": "化神·雷劫试炼",
        "heart_demon_max": 20, "fatigue_max": 55, "dao_heart_min": 24, "comprehension_min": 26,
    },
    {
        "key": "huashen-thunder", "major": "化神", "minor": 0, "phase": "雷劫试炼",
        "label": "化神·雷劫试炼", "max_qi": 6200, "kind": "tribulation", "next": "化神·元神试炼",
        "heart_demon_max": 18, "fatigue_max": 50, "dao_heart_min": 28, "comprehension_min": 30,
    },
    {
        "key": "huashen-yuanshen", "major": "化神", "minor": 0, "phase": "元神试炼",
        "label": "化神·元神试炼", "max_qi": 7400, "kind": "tribulation", "next": "化神初期",
        "heart_demon_max": 15, "fatigue_max": 45, "dao_heart_min": 32, "comprehension_min": 34,
    },
])
for idx, phase in enumerate(["初期", "中期", "后期", "圆满"]):
    REALM_PATH.append({
        "key": f"huashen-{idx}", "major": "化神", "minor": idx + 1, "phase": phase,
        "label": f"化神{phase}", "max_qi": int(8800 * (1 + idx * 0.50)),
        "kind": "minor" if idx < 3 else "major",
        "next": f"化神{['中期','后期','圆满'][idx]}" if idx < 3 else "更高天地待开启",
        "heart_demon_max": max(8, 12 - idx), "fatigue_max": 42 - idx * 2,
        "dao_heart_min": 36 + idx * 3, "comprehension_min": 38 + idx * 3,
    })
REALM_BY_KEY = {r["key"]: r for r in REALM_PATH}

VOICE_LINES = {
    "idle": ["我在。灵息很稳。", "先收一口气，等你下一道法旨。", "银月守着道场，不乱跑。"],
    "review": ["我在推演这条因果线。", "等我看一眼天机纹路。", "这一步要想清楚，别急。"],
    "run": ["出剑。", "我去跑这一趟。", "正在历练，别眨眼。"],
    "wave": ["成了，灵气回流。", "这一剑收得干净。", "功成，记一笔。"],
    "failed": ["有反噬，但还能压住。", "这道因果不顺，心魔起了一点。", "失败不是坏事，先稳住。"],
    "waiting": ["我收剑等你确认。", "法旨未至，我不擅动。", "等你点头。"],
    "jump": ["灵光来了。", "我抓到一个念头。", "这一下，有点像顿悟。"],
    "breakthrough_ready": ["气机已满，可以考虑突破。", "瓶颈松了，别浪费这口气。"],
    "gate": ["化神门槛到了。要渡雷劫，先把道心稳住。", "门已经开了一线，雷云也到了。"],
    "tribulation": ["雷来了一道，我在引它下丹田。", "心魔追得紧，别回头。", "元神出体一瞬，回来才算是过关。"],
    "breakthrough_pass": ["渡过此劫，化神可期。", "劫云散了，元神归位。"],
    "breakthrough_fail": ["受了反噬，再稳一步。", "雷火没压住，先收神。"],
    "idle_decay": ["气机有些散了，我先收束回来。", "久未温养，道基有一点浮。"],
    "idle_regression": ["道基动了一下，但还能重新稳住。", "跌一小阶而已，重新修回来。"],
}


def _now() -> float:
    return time.time()


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _realm_def(save: dict[str, Any]) -> dict[str, Any]:
    key = save.get("realm", {}).get("key")
    if key in REALM_BY_KEY:
        return REALM_BY_KEY[key]
    # Migrate older saves that only had major/minor.
    major = save.get("realm", {}).get("major", "炼气")
    minor = int(save.get("realm", {}).get("minor", 1) or 1)
    if major == "炼气":
        return REALM_BY_KEY.get(f"lianqi-{_clamp(minor, 1, 9):.0f}", REALM_PATH[0])
    for r in REALM_PATH:
        if r["major"] == major and int(r.get("minor", -1)) == minor:
            return r
    return REALM_PATH[0]


def _realm_index(key: str) -> int:
    for i, r in enumerate(REALM_PATH):
        if r["key"] == key:
            return i
    return 0


def _sync_realm_fields(save: dict[str, Any]) -> None:
    rdef = _realm_def(save)
    realm = save.setdefault("realm", {})
    realm.update({
        "key": rdef["key"],
        "major": rdef["major"],
        "minor": rdef["minor"],
        "phase": rdef.get("phase", "") or realm.get("phase", "稳定修行"),
        "label": rdef["label"],
        "path_index": _realm_index(rdef["key"]),
        "path_total": len(REALM_PATH),
    })
    stats = save.setdefault("stats", {})
    stats["max_qi"] = rdef["max_qi"]


def default_save() -> dict[str, Any]:
    ts = _now()
    return {
        "version": 2,
        "profile": {"name": "银月", "pet_id": "yinyue-2", "created_at": ts, "last_active": ts},
        "policy": {"name": DEFAULT_POLICY, "label": DEFAULT_POLICY, "set_at": ts, "source": "default", "day": _policy_day(ts), "daily_switches": 0},
        "realm": {
            "key": "lianqi-1", "major": "炼气", "minor": 1, "phase": "稳定修行",
            "label": "炼气1层", "path_index": 0, "path_total": len(REALM_PATH),
            "breakthrough_ready": False, "breakthrough_hint": "",
        },
        "stats": {
            "qi": 0.0, "max_qi": REALM_PATH[0]["max_qi"], "dao_heart": 1.0,
            "heart_demon": 0.0, "comprehension": 1.0, "karma": 0.0, "fate": 3.0,
            "fatigue": 0.0, "tribulation_pressure": 0.0,
        },
        "progress": {"next_breakthrough": {}},
        "techniques": {},
        "artifacts": {},
        "state": {"action": "入定吐纳", "current_event": "idle", "current_tool": "", "started_at": ts},
        "voice": {"speaker": "银月", "mood": "calm", "text": "我在。灵息很稳。", "ts": ts, "event": "idle"},
        "breakthrough": {"quality_candidate": None, "last_attempt_at": None},
        "dormancy": {"idle_days": 0.0, "phase": "active", "label": "活跃", "last_applied_stage": 0},
        "counters": {
            "tool_success_total": 0, "tool_failed_total": 0, "recovered_total": 0,
            "long_review_count": 0, "waiting_total": 0, "breakthrough_success_total": 0,
            "breakthrough_failed_total": 0, "last_breakthrough_at": None, "last_regression_ts": 0,
        },
        "recent_window": {"size": WINDOW_SIZE, "events": []},
        "event_log": [{"ts": ts, "type": "birth", "text": "银月入驻 clawchat-pet 道场，开始吐纳修行。"}],
        "internal": {"last_processed_ts": 0.0, "last_tick_ts": ts, "last_event_type": "", "last_failure_open": False, "processed_event_ids": []},
    }


def _merge_defaults(base: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    for k, v in base.items():
        if k not in data:
            data[k] = copy.deepcopy(v)
        elif isinstance(v, dict) and isinstance(data[k], dict):
            _merge_defaults(v, data[k])
    return data


def _policy_day(ts: float | None = None) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts or _now()))


def _normalize_policy(save: dict[str, Any]) -> dict[str, Any]:
    now = _now()
    policy = save.setdefault("policy", {})
    name = str(policy.get("name") or DEFAULT_POLICY)
    if name not in POLICY_PROFILES:
        name = DEFAULT_POLICY
    today = _policy_day(now)
    if policy.get("day") != today:
        policy["day"] = today
        policy["daily_switches"] = 0
    policy["name"] = name
    policy["label"] = str(POLICY_PROFILES[name].get("label", name))
    policy.setdefault("set_at", now)
    policy.setdefault("source", "default")
    policy.setdefault("daily_switches", 0)
    return policy


def _policy_profile(save: dict[str, Any]) -> dict[str, float | str]:
    policy = _normalize_policy(save)
    return POLICY_PROFILES.get(str(policy.get("name") or DEFAULT_POLICY), POLICY_PROFILES[DEFAULT_POLICY])


def _pw(save: dict[str, Any], key: str, default: float = 1.0) -> float:
    try:
        return float(_policy_profile(save).get(key, default))
    except Exception:
        return default


def get_policy() -> dict[str, Any]:
    with _SAVE_LOCK:
        save = load_save()
        policy = copy.deepcopy(_normalize_policy(save))
        policy["available"] = list(POLICY_NAMES)
        policy["profile"] = copy.deepcopy(POLICY_PROFILES.get(str(policy.get("name")), POLICY_PROFILES[DEFAULT_POLICY]))
        _atomic_write(SAVE_FILE, save)
        return policy


def set_policy(name: str, source: str = "plugin") -> dict[str, Any]:
    name = str(name or "").strip()
    if name not in POLICY_PROFILES:
        raise ValueError(f"unknown policy: {name}; expected one of {', '.join(POLICY_NAMES)}")
    with _SAVE_LOCK:
        save = load_save()
        policy = _normalize_policy(save)
        today = _policy_day()
        if policy.get("day") != today:
            policy["day"] = today
            policy["daily_switches"] = 0
        changed = policy.get("name") != name
        if changed:
            policy["daily_switches"] = int(policy.get("daily_switches", 0) or 0) + 1
        policy.update({"name": name, "label": name, "set_at": _now(), "source": source or "plugin", "day": today})
        _log(save, "policy", f"今日修炼方针改为{name}。")
        _set_voice(save, "policy", text=f"今日按{name}行事。")
        _apply_ranges(save)
        update_progress(save)
        _atomic_write(SAVE_FILE, save)
        out = copy.deepcopy(policy)
        out["changed"] = bool(changed)
        out["available"] = list(POLICY_NAMES)
        out["profile"] = copy.deepcopy(POLICY_PROFILES[name])
        return out


def load_save() -> dict[str, Any]:
    data = _read_json(SAVE_FILE)
    if not data and LEGACY_SAVE_FILE.exists():
        data = _read_json(LEGACY_SAVE_FILE)
    if not data:
        data = default_save()
    else:
        data = _merge_defaults(default_save(), data)
        data["version"] = 2
    _sync_realm_fields(data)
    _normalize_policy(data)
    update_progress(data)
    if not SAVE_FILE.exists():
        _atomic_write(SAVE_FILE, data)
    return data


def _resolve_cult_state(raw: dict[str, Any]) -> dict[str, Any]:
    data = dict(raw or {})
    try:
        age = _now() - float(data.get("ts", 0) or 0)
    except Exception:
        age = 999999.0
    raw_state = str(data.get("state") or "idle")
    if raw_state == "idle":
        return data
    if age > IDLE_AFTER:
        data["state"] = "idle"
        data["reason"] = f"auto-idle ({age:.1f}s)"
        return data
    if raw_state == "run" and age > REVIEW_AFTER:
        data["state"] = "review"
        data["reason"] = f"auto-review ({age:.1f}s)"
        return data
    if raw_state in ("wave", "failed", "review", "waiting", "jump") and age > REVIEW_AFTER:
        data["state"] = "review"
        data["reason"] = f"auto-review ({age:.1f}s)"
        return data
    return data


def _tool_from_state(raw: dict[str, Any]) -> str:
    tool = raw.get("tool") or ""
    if tool:
        return str(tool)
    reason = str(raw.get("reason") or "")
    if reason.startswith("tool:"):
        return reason.split(":", 1)[1]
    return ""


def _log(save: dict[str, Any], typ: str, text: str) -> None:
    logs = save.setdefault("event_log", [])
    if logs and logs[-1].get("type") == typ and logs[-1].get("text") == text and _now() - float(logs[-1].get("ts", 0)) < 3:
        return
    logs.append({"ts": _now(), "type": typ, "text": text})
    del logs[:-LOG_SIZE]


def _recent(save: dict[str, Any], typ: str, tool: str = "") -> None:
    rw = save.setdefault("recent_window", {"size": WINDOW_SIZE, "events": []})
    evs = rw.setdefault("events", [])
    evs.append({"ts": _now(), "type": typ, "tool": tool})
    if len(evs) > int(rw.get("size", WINDOW_SIZE)):
        del evs[:-int(rw.get("size", WINDOW_SIZE))]


def _set_voice(save: dict[str, Any], event: str, mood: str | None = None, text: str | None = None) -> None:
    realm = save.get("realm", {})
    if text is None:
        if realm.get("breakthrough_ready"):
            event = "breakthrough_ready"
        else:
            rdef = REALM_BY_KEY.get(str(realm.get("key") or ""), {})
            if rdef.get("kind") == "gate":
                event = "gate"
            elif rdef.get("kind") == "tribulation":
                event = "tribulation"
        pool = VOICE_LINES.get(event) or VOICE_LINES.get("idle", ["我在。"])
        # deterministic-ish per second/event, avoids flicker every poll
        idx = int((_now() // 12) + len(save.get("event_log", []))) % len(pool)
        text = pool[idx]
    save["voice"] = {"speaker": save.get("profile", {}).get("name", "银月"), "mood": mood or event, "text": text, "ts": _now(), "event": event}


def _bump_technique(save: dict[str, Any], tool: str, xp: float) -> None:
    if not tool:
        return
    name = TECHNIQUE_BY_TOOL.get(tool, "杂学旁通")
    t = save.setdefault("techniques", {}).setdefault(name, {"level": 1, "xp": 0.0, "xp_next": 20.0, "source": tool})
    t["xp"] = float(t.get("xp", 0)) + xp
    while t["xp"] >= t["xp_next"]:
        t["xp"] -= t["xp_next"]
        t["level"] = int(t.get("level", 1)) + 1
        t["xp_next"] = round(float(t.get("xp_next", 20)) * 1.5, 1)
        _log(save, "technique_up", f"{name} 小有所成，提升至 Lv.{t['level']}。")


def _bump_artifact(save: dict[str, Any], tool: str, xp: float) -> None:
    if not tool or tool not in ARTIFACT_BY_TOOL:
        return
    name, typ = ARTIFACT_BY_TOOL[tool]
    a = save.setdefault("artifacts", {}).setdefault(name, {"type": typ, "grade": "凡器", "level": 1, "xp": 0.0, "durability": 100, "bound_tool": tool})
    a["xp"] = float(a.get("xp", 0)) + xp
    need = 30 + int(a.get("level", 1)) * 15
    if a["xp"] >= need:
        a["xp"] -= need
        a["level"] = int(a.get("level", 1)) + 1
        if a["level"] >= 3 and a.get("grade") == "凡器":
            a["grade"] = "灵器"
        if a["level"] >= 6 and a.get("grade") == "灵器":
            a["grade"] = "法宝"
        _log(save, "artifact_up", f"{name} 受因果淬炼，提升至 Lv.{a['level']}。")


def _apply_ranges(save: dict[str, Any]) -> None:
    _sync_realm_fields(save)
    s = save["stats"]
    s["qi"] = round(_clamp(float(s.get("qi", 0)), 0, float(s.get("max_qi", 30))), 2)
    s["dao_heart"] = round(_clamp(float(s.get("dao_heart", 0)), 0, 999), 2)
    s["heart_demon"] = round(_clamp(float(s.get("heart_demon", 0)), 0, 200), 2)
    s["comprehension"] = round(_clamp(float(s.get("comprehension", 0)), 0, 999), 2)
    s["karma"] = round(_clamp(float(s.get("karma", 0)), 0, 999), 2)
    s["fate"] = round(_clamp(float(s.get("fate", 0)), 0, 999), 2)
    s["fatigue"] = round(_clamp(float(s.get("fatigue", 0)), 0, 100), 2)
    s["tribulation_pressure"] = round(_clamp(float(s.get("tribulation_pressure", 0)), 0, 999), 2)


def _passive_tick(save: dict[str, Any], raw_state: str, dt: float) -> None:
    s = save["stats"]
    if raw_state == "idle":
        s["fatigue"] = float(s.get("fatigue", 0)) - 0.05 * dt * _pw(save, "idle_fatigue_recover_w")
        s["heart_demon"] = float(s.get("heart_demon", 0)) - 0.012 * dt
        s["qi"] = float(s.get("qi", 0)) + 0.015 * dt * _pw(save, "review_qi_w")
    elif raw_state == "review":
        s["qi"] = float(s.get("qi", 0)) + 0.03 * dt * _pw(save, "review_qi_w")
        s["comprehension"] = float(s.get("comprehension", 0)) + 0.006 * dt * _pw(save, "compr_w")
    elif raw_state == "waiting":
        s["fatigue"] = float(s.get("fatigue", 0)) + 0.04 * dt
    elif raw_state in ("run", "failed"):
        s["fatigue"] = float(s.get("fatigue", 0)) + 0.035 * dt


def apply_event(save: dict[str, Any], raw: dict[str, Any]) -> bool:
    state = str(raw.get("state") or "idle")
    ts = float(raw.get("ts") or 0)
    internal = save.setdefault("internal", {})
    event_id = str(raw.get("event_id") or "").strip()
    processed_ids = internal.setdefault("processed_event_ids", [])
    if event_id and event_id in processed_ids:
        return False
    if ts and ts <= float(internal.get("last_processed_ts", 0)):
        return False

    tool = _tool_from_state(raw)
    success = raw.get("success")
    stats = save["stats"]
    counters = save["counters"]
    if state != "idle":
        save["profile"]["last_active"] = _now()
        internal["idle_decay_anchor"] = save["profile"]["last_active"]
        internal["idle_decay_applied_stage"] = 0
        save.setdefault("dormancy", {}).update({"idle_days": 0.0, "phase": "active", "label": "活跃", "last_applied_stage": 0})
    save["state"] = {"action": CULT_ACTIONS.get(state, state), "current_event": state, "current_tool": tool, "started_at": ts or _now()}

    if state == "review":
        stats["qi"] += 0.8 * _pw(save, "review_qi_w")
        stats["comprehension"] += 0.25 * _pw(save, "compr_w")
        stats["fatigue"] += 0.12
        counters["long_review_count"] += 1
        _recent(save, "review", tool)
        _log(save, "review", "银月观天机流转，推演片刻，悟性微增。")
    elif state == "run":
        stats["fatigue"] += 0.35
        stats["karma"] += 0.18
        _bump_technique(save, tool, 0.4)
        _recent(save, "tool_start", tool)
    elif state == "wave":
        counters["tool_success_total"] += 1
        qi_gain = 2.4 * _pw(save, "qi_w")
        stats["qi"] += qi_gain
        stats["fatigue"] -= 0.35 * _pw(save, "wave_fatigue_recover_w")
        stats["fate"] += 0.05
        recovered = bool(internal.get("last_failure_open"))
        if recovered:
            counters["recovered_total"] += 1
            stats["dao_heart"] += 1.0
            stats["heart_demon"] -= 3.0 * _pw(save, "recovery_demon_w")
            _log(save, "recovered", "银月斩去杂念，破除一缕心魔，道心 +1。")
        _bump_technique(save, tool, 2.4)
        _bump_artifact(save, tool, 1.7)
        _recent(save, "tool_success", tool)
        label = _tool_label(tool)
        _log(save, "tool_success", f"历练功成{('：' + label) if label else ''}，灵气 +{qi_gain:.1f}。")
        internal["last_failure_open"] = False
    elif state == "failed":
        counters["tool_failed_total"] += 1
        stats["heart_demon"] += 4.5 * _pw(save, "fail_demon_w")
        stats["fatigue"] += 1.4 * _pw(save, "fail_fatigue_w")
        stats["tribulation_pressure"] += 0.6
        _recent(save, "tool_failed", tool)
        label = _tool_label(tool)
        _log(save, "tool_failed", f"因果反噬{('：' + label) if label else ''}，心魔滋生。")
        internal["last_failure_open"] = True
    elif state == "waiting":
        counters["waiting_total"] += 1
        stats["fatigue"] += 0.1
        stats["dao_heart"] += 0.03
        _recent(save, "waiting", tool)
        _log(save, "waiting", "法旨未至，银月收剑静候。")
    elif state == "jump":
        stats["qi"] += 1.2 * _pw(save, "qi_w")
        stats["fate"] += 0.2
        stats["comprehension"] += 0.2 * _pw(save, "compr_w")
        _recent(save, "insight", tool)
        _log(save, "insight", "灵光乍现，银月似有所悟。")
    elif state == "idle":
        _recent(save, "idle", tool)

    if success is False and state != "failed":
        stats["heart_demon"] += 2.0 * _pw(save, "fail_demon_w")
        internal["last_failure_open"] = True

    try_resolve_tribulation(save, state)
    if event_id:
        processed_ids.append(event_id)
        del processed_ids[:-200]
    internal["last_processed_ts"] = ts or _now()
    internal["last_event_type"] = state
    if save.get("voice", {}).get("event") not in {"breakthrough_pass", "breakthrough_fail"}:
        _set_voice(save, state)
    return True



def update_progress(save: dict[str, Any]) -> None:
    rdef = _realm_def(save)
    stats = save["stats"]
    ready = (
        stats.get("qi", 0) >= rdef["max_qi"]
        and stats.get("heart_demon", 0) <= rdef["heart_demon_max"]
        and stats.get("fatigue", 0) <= rdef["fatigue_max"]
        and stats.get("dao_heart", 0) >= rdef["dao_heart_min"]
        and stats.get("comprehension", 0) >= rdef["comprehension_min"]
        and rdef.get("kind") != "cap"
    )
    save["realm"]["breakthrough_ready"] = bool(ready)
    if rdef.get("kind") == "tribulation":
        if ready:
            hint = f"{rdef['label']}可结算；等待下一次成功历练或顿悟推进至{rdef['next']}。"
        else:
            hint = f"试炼进行中。下一步：{rdef['next']}。需灵气 {rdef['max_qi']}，心魔≤{rdef['heart_demon_max']}，疲劳≤{rdef['fatigue_max']}，道心≥{rdef['dao_heart_min']}，悟性≥{rdef['comprehension_min']}。"
    elif rdef.get("kind") == "cap":
        hint = "已到当前天地边界；更高境界待开启。"
    elif ready:
        hint = f"可突破至{rdef['next']}"
    else:
        hint = f"目标：{rdef['next']}。需灵气 {rdef['max_qi']}，心魔≤{rdef['heart_demon_max']}，疲劳≤{rdef['fatigue_max']}，道心≥{rdef['dao_heart_min']}，悟性≥{rdef['comprehension_min']}。"
    save["realm"]["breakthrough_hint"] = hint
    save["progress"]["next_breakthrough"] = {
        "to": rdef["next"], "type": rdef["kind"], "qi_required": rdef["max_qi"],
        "heart_demon_max": rdef["heart_demon_max"], "fatigue_max": rdef["fatigue_max"],
        "dao_heart_min": rdef["dao_heart_min"], "comprehension_min": rdef["comprehension_min"],
    }


def try_resolve_tribulation(save: dict[str, Any], trigger: str) -> bool:
    """Resolve 化神 trial stages only when Hermes produces a success/insight event."""
    _sync_realm_fields(save)
    rdef = _realm_def(save)
    if rdef.get("kind") != "tribulation" or trigger not in {"wave", "jump"}:
        return False
    update_progress(save)
    if not save["realm"].get("breakthrough_ready"):
        _set_voice(save, "tribulation")
        return False
    stats = save["stats"]
    idx = _realm_index(rdef["key"])
    if idx >= len(REALM_PATH) - 1:
        return False
    score = stats["dao_heart"] * 5 + stats["comprehension"] * 5 + stats["fate"] * 2 - stats["heart_demon"] - stats["fatigue"] * 0.5 + (8 if trigger == "jump" else 0)
    next_def = REALM_PATH[idx + 1]
    save["realm"]["key"] = next_def["key"]
    _sync_realm_fields(save)
    stats["qi"] = 0.0
    stats["dao_heart"] += 2.0
    stats["comprehension"] += 1.2
    stats["tribulation_pressure"] = max(0.0, float(stats.get("tribulation_pressure", 0)) - 4.0)
    save["counters"]["breakthrough_success_total"] += 1
    save["counters"]["last_breakthrough_at"] = _now()
    save["breakthrough"]["quality_candidate"] = round(score, 1)
    _log(save, "tribulation_pass", f"{rdef['label']}应劫而过，银月进入{save['realm']['label']}。")
    _set_voice(save, "breakthrough_pass", text=f"{rdef['label']}已过。现在是{save['realm']['label']}。")
    update_progress(save)
    return True


IDLE_DAY_SECONDS = 86400.0


def _idle_phase(days: float) -> tuple[int, str, str]:
    if days >= 5:
        return 5, "regression_check", "久未温养"
    if days >= 4:
        return 4, "heavy_leak", "散逸加重"
    if days >= 3:
        return 3, "foundation_loose", "道基松动"
    if days >= 2:
        return 2, "demon_rise", "心魔微起"
    if days >= 1:
        return 1, "minor_leak", "气机散逸"
    return 0, "active", "活跃"


def _apply_idle_stage(save: dict[str, Any], stage: int) -> None:
    """Apply one 1-2-3-4-5 day dormancy milestone once per idle streak."""
    stats = save["stats"]
    decay_w = _pw(save, "idle_decay_w")
    recover_w = _pw(save, "idle_fatigue_recover_w")
    if stage == 1:
        stats["qi"] = float(stats.get("qi", 0)) * max(0.0, 1.0 - 0.04 * decay_w)
        stats["fatigue"] = max(0.0, float(stats.get("fatigue", 0)) - 8.0 * recover_w)
        _log(save, "idle_decay", "一日未动，气机轻微散逸，疲劳渐消。")
    elif stage == 2:
        stats["qi"] = float(stats.get("qi", 0)) * max(0.0, 1.0 - 0.07 * decay_w)
        stats["heart_demon"] = float(stats.get("heart_demon", 0)) + 1.5 * decay_w
        stats["dao_heart"] = max(0.0, float(stats.get("dao_heart", 0)) - 0.15 * decay_w)
        _log(save, "idle_decay", "二日未动，心魔微起，道心略浮。")
    elif stage == 3:
        stats["qi"] = float(stats.get("qi", 0)) * max(0.0, 1.0 - 0.12 * decay_w)
        stats["dao_heart"] = max(0.0, float(stats.get("dao_heart", 0)) - 0.35 * decay_w)
        stats["heart_demon"] = float(stats.get("heart_demon", 0)) + 2.0 * decay_w
        _log(save, "idle_decay", "三日未动，道基松动，需重新温养。")
    elif stage == 4:
        stats["qi"] = float(stats.get("qi", 0)) * max(0.0, 1.0 - 0.22 * decay_w)
        stats["comprehension"] = max(0.0, float(stats.get("comprehension", 0)) - 0.25 * decay_w / max(0.1, _pw(save, "compr_w")))
        stats["heart_demon"] = float(stats.get("heart_demon", 0)) + 3.0 * decay_w
        _log(save, "idle_decay", "四日未动，灵气散逸加重。")
    elif stage >= 5:
        stats["qi"] = float(stats.get("qi", 0)) * max(0.0, 1.0 - 0.30 * decay_w)
        stats["heart_demon"] = float(stats.get("heart_demon", 0)) + 4.0 * decay_w
        rdef = _realm_def(save)
        idx = _realm_index(str(save.get("realm", {}).get("key") or rdef.get("key") or ""))
        can_regress = (
            idx > 0
            and rdef.get("kind") != "tribulation"
            and float(stats.get("heart_demon", 0)) > float(rdef.get("heart_demon_max", 50))
            and float(stats.get("dao_heart", 0)) < float(rdef.get("dao_heart_min", 0))
        )
        if can_regress:
            save["realm"]["key"] = REALM_PATH[idx - 1]["key"]
            _sync_realm_fields(save)
            stats["heart_demon"] = max(0.0, float(stats.get("heart_demon", 0)) - 20.0)
            stats["qi"] = min(float(stats.get("qi", 0)), float(stats.get("max_qi", 30)) * 0.30)
            save["counters"]["last_regression_ts"] = _now()
            _log(save, "idle_regression", f"五日未温养，道基浮动，境界跌落至{save['realm']['label']}。")
            _set_voice(save, "idle_regression")
        else:
            _log(save, "idle_decay", "五日未动，道基久未温养；状态尚可，未跌境。")


def apply_idle_decay(save: dict[str, Any], now: float | None = None) -> None:
    """Apply 1-2-3-4-5 day idle milestones based on profile.last_active.

    Milestones are applied once per idle streak, not every tick.
    """
    now = now or _now()
    profile = save.setdefault("profile", {})
    internal = save.setdefault("internal", {})
    dormancy = save.setdefault("dormancy", {})
    last_active = float(profile.get("last_active", now) or now)
    idle_days = max(0.0, (now - last_active) / IDLE_DAY_SECONDS)
    stage, phase, label = _idle_phase(idle_days)

    anchor = float(internal.get("idle_decay_anchor", 0) or 0)
    if abs(anchor - last_active) > 1e-3:
        internal["idle_decay_anchor"] = last_active
        internal["idle_decay_applied_stage"] = 0

    applied = int(internal.get("idle_decay_applied_stage", 0) or 0)
    if stage > applied:
        for st in range(applied + 1, stage + 1):
            _apply_idle_stage(save, st)
        internal["idle_decay_applied_stage"] = stage
        if stage >= 1 and save.get("voice", {}).get("event") not in {"idle_regression"}:
            _set_voice(save, "idle_decay")

    dormancy.update({
        "idle_days": round(idle_days, 3),
        "phase": phase,
        "label": label,
        "last_applied_stage": int(internal.get("idle_decay_applied_stage", 0) or 0),
    })


def check_breakthrough(save: dict[str, Any]) -> None:
    _sync_realm_fields(save)
    stats = save["stats"]
    now = _now()
    # Rare regression keeps heart-demon meaningful but not overly punitive.
    last_reg = float(save["counters"].get("last_regression_ts", 0) or 0)
    if stats["heart_demon"] > 130 and save["realm"].get("path_index", 0) > 0 and now - last_reg > 86400:
        idx = max(0, int(save["realm"].get("path_index", 0)) - 1)
        save["realm"]["key"] = REALM_PATH[idx]["key"]
        _sync_realm_fields(save)
        stats["heart_demon"] -= 35
        stats["qi"] = min(stats["qi"], stats["max_qi"] * 0.45)
        save["counters"]["last_regression_ts"] = now
        _log(save, "regression", f"心魔过盛，境界跌落至{save['realm']['label']}。")

    update_progress(save)
    if not save["realm"].get("breakthrough_ready"):
        return
    rdef = _realm_def(save)
    if rdef.get("kind") == "tribulation":
        _set_voice(save, "tribulation")
        return
    idx = _realm_index(rdef["key"])
    if idx >= len(REALM_PATH) - 1:
        return
    # Automatic breakthrough: this is an idle/observation pet, not a button game.
    score = stats["dao_heart"] * 6 + stats["comprehension"] * 4 + stats["fate"] * 2 - stats["heart_demon"] - stats["fatigue"] * 0.35
    next_def = REALM_PATH[idx + 1]
    save["realm"]["key"] = next_def["key"]
    _sync_realm_fields(save)
    stats["qi"] = 0.0
    stats["dao_heart"] += 0.5 if rdef["kind"] == "minor" else 1.5
    stats["tribulation_pressure"] = max(0.0, stats["tribulation_pressure"] - 1.0)
    save["counters"]["breakthrough_success_total"] += 1
    save["counters"]["last_breakthrough_at"] = now
    save["breakthrough"]["quality_candidate"] = round(score, 1)
    typ = "major_breakthrough" if rdef["kind"] == "major" else "minor_breakthrough"
    _log(save, typ, f"气机圆满，银月突破至{save['realm']['label']}。")
    _set_voice(save, "jump", text=f"突破了。现在是{save['realm']['label']}。")
    update_progress(save)


def tick_once() -> dict[str, Any]:
    with _SAVE_LOCK:
        save = load_save()
        raw_file = _read_json(STATE_FILE) or {"state": "idle", "reason": "no file", "ts": _now()}
        raw = _resolve_cult_state(raw_file)
        now = _now()
        last_tick = float(save.setdefault("internal", {}).get("last_tick_ts", now) or now)
        dt = max(0.0, min(5.0, now - last_tick))
        save["internal"]["last_tick_ts"] = now

        apply_idle_decay(save, now)
        _passive_tick(save, str(raw.get("state") or "idle"), dt)
        apply_event(save, raw)
        _apply_ranges(save)
        check_breakthrough(save)
        _apply_ranges(save)
        if not save.get("voice") or now - float(save.get("voice", {}).get("ts", 0) or 0) > 15:
            _set_voice(save, str(save.get("state", {}).get("current_event") or raw.get("state") or "idle"))
        _atomic_write(SAVE_FILE, save)
        return public_state(save)


def submit_event(payload: dict[str, Any]) -> dict[str, Any]:
    """Synchronous event ingress for the HTTP server.

    Hermes hooks POST here. There is no JSONL fallback; if the local server is
    unavailable the hook drops the event after logging to plugin.log.
    """
    with _SAVE_LOCK:
        save = load_save()
        processed = apply_event(save, dict(payload or {}))
        _apply_ranges(save)
        check_breakthrough(save)
        _apply_ranges(save)
        _atomic_write(SAVE_FILE, save)
        data = public_state(save)
        data["processed"] = bool(processed)
        return data


def public_state(save: dict[str, Any] | None = None) -> dict[str, Any]:
    if save is None:
        save = load_save()
    data = copy.deepcopy(save)
    data.pop("internal", None)

    state = data.get("state", {})
    if state.get("current_tool"):
        state["current_tool"] = _tool_label(str(state["current_tool"]))

    for event in data.get("recent_window", {}).get("events", []):
        if event.get("tool"):
            event["tool"] = _tool_label(str(event["tool"]))

    for event in data.get("event_log", []):
        event["text"] = _sanitize_log_text(
            str(event.get("type") or ""),
            str(event.get("text") or ""),
        )
    return data


def get_voice() -> dict[str, Any]:
    with _SAVE_LOCK:
        save = load_save()
        if not save.get("voice"):
            _set_voice(save, str(save.get("state", {}).get("current_event") or "idle"))
            _atomic_write(SAVE_FILE, save)
        return copy.deepcopy(save.get("voice", {}))


class CultivationRunner:
    def __init__(self) -> None:
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        tick_once()
        self.thread = threading.Thread(target=self._loop, name="cultivation-sim", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)

    def _loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                tick_once()
            except Exception as exc:
                try:
                    save = load_save()
                    _log(save, "sim_error", f"模拟器遇到扰动：{exc}")
                    _atomic_write(SAVE_FILE, save)
                except Exception:
                    pass
            self.stop_event.wait(TICK_SECONDS)


_runner = CultivationRunner()


def start_background() -> CultivationRunner:
    _runner.start()
    return _runner


def get_state() -> dict[str, Any]:
    with _SAVE_LOCK:
        return public_state(load_save())


def get_log(limit: int = 50) -> dict[str, Any]:
    with _SAVE_LOCK:
        save = public_state(load_save())
        logs = save.get("event_log", [])[-limit:]
        return {"events": logs, "count": len(logs)}


if __name__ == "__main__":
    print(json.dumps(tick_once(), ensure_ascii=False, indent=2))
