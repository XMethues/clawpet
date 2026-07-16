from __future__ import annotations

import copy
import json
import os
import re
import time
from pathlib import Path
from typing import Any

HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
DATA_DIR = HERMES_HOME / "clawchat-pet"
SKINS_FILE = DATA_DIR / "skins.json"

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,48}$")

BUILTIN_SKINS: dict[str, dict[str, Any]] = {
    "qingming": {
        "id": "qingming",
        "name": "青冥道场",
        "source": "builtin",
        "description": "青蓝、清净、稳定。适合入定与悟道。",
        "mood": ["青蓝", "清净", "稳定"],
        "suitable_policies": ["入定", "悟道"],
        "suitable_states": ["稳定", "推演", "轻度闲置"],
        "rules_effect": "none",
        "visual": {
            "bgMain": "radial-gradient(circle at 50% 0%, rgba(76, 135, 180, 0.24), transparent 34%), linear-gradient(180deg, #0b1d2a 0%, #0a0d18 100%)",
            "panel": "rgba(11, 21, 35, 0.84)",
            "panelSoft": "rgba(12, 28, 44, 0.74)",
            "accent": "#65c8ff",
            "accentSoft": "rgba(101, 200, 255, 0.38)",
            "textMain": "#d4eaff",
            "textMuted": "#89a8c0",
            "gold": "#f0db9a",
            "border": "rgba(93, 151, 186, 0.44)",
            "track": "rgba(30, 53, 72, 0.78)",
            "bubbleBg": "rgba(10, 25, 38, 0.88)",
            "bubbleBorder": "rgba(120, 190, 230, 0.36)",
            "bubbleText": "#d7ecff",
            "qi": "#65c8ff",
            "demon": "#d96e7a",
            "glow": "rgba(101, 200, 255, 0.16)",
        },
    },
    "chiyan": {
        "id": "chiyan",
        "name": "赤焰道场",
        "source": "builtin",
        "description": "赤红、金橙、烈焰。适合冲关氛围，但不提高冲关成功率。",
        "mood": ["赤红", "烈焰", "进取"],
        "suitable_policies": ["冲关"],
        "suitable_states": ["临近突破", "气机充盈", "试炼前夜"],
        "rules_effect": "none",
        "visual": {
            "bgMain": "radial-gradient(circle at 50% 0%, rgba(255, 117, 50, 0.28), transparent 36%), linear-gradient(180deg, #27110d 0%, #100b12 100%)",
            "panel": "rgba(45, 18, 13, 0.84)",
            "panelSoft": "rgba(58, 23, 12, 0.76)",
            "accent": "#ff9b45",
            "accentSoft": "rgba(255, 155, 69, 0.42)",
            "textMain": "#ffe1c1",
            "textMuted": "#c89472",
            "gold": "#ffd36e",
            "border": "rgba(224, 117, 64, 0.50)",
            "track": "rgba(82, 35, 24, 0.80)",
            "bubbleBg": "rgba(48, 18, 13, 0.88)",
            "bubbleBorder": "rgba(255, 154, 77, 0.42)",
            "bubbleText": "#ffe3cc",
            "qi": "#ffb347",
            "demon": "#ff6170",
            "glow": "rgba(255, 119, 46, 0.20)",
        },
    },
    "xuanshui": {
        "id": "xuanshui",
        "name": "玄水道场",
        "source": "builtin",
        "description": "深蓝、水纹、安静。适合调息与淬心，但不降低心魔数值。",
        "mood": ["深蓝", "水纹", "沉静"],
        "suitable_policies": ["调息", "淬心"],
        "suitable_states": ["疲劳偏高", "心魔偏高", "恢复"],
        "rules_effect": "none",
        "visual": {
            "bgMain": "radial-gradient(circle at 50% 0%, rgba(56, 211, 214, 0.20), transparent 34%), linear-gradient(180deg, #071929 0%, #06101d 100%)",
            "panel": "rgba(7, 24, 39, 0.86)",
            "panelSoft": "rgba(8, 34, 54, 0.76)",
            "accent": "#5fe7dc",
            "accentSoft": "rgba(95, 231, 220, 0.36)",
            "textMain": "#d4ffff",
            "textMuted": "#80b8bc",
            "gold": "#ccebd8",
            "border": "rgba(84, 189, 190, 0.44)",
            "track": "rgba(22, 61, 77, 0.80)",
            "bubbleBg": "rgba(6, 31, 47, 0.90)",
            "bubbleBorder": "rgba(95, 231, 220, 0.36)",
            "bubbleText": "#d7ffff",
            "qi": "#5fe7dc",
            "demon": "#b47cff",
            "glow": "rgba(95, 231, 220, 0.16)",
        },
    },
}

DEFAULT_SKIN = "qingming"
DEFAULT_UNLOCKED = ["qingming", "chiyan", "xuanshui"]


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _default_store() -> dict[str, Any]:
    return {"version": 1, "active_skin": DEFAULT_SKIN, "unlocked": list(DEFAULT_UNLOCKED), "custom": []}


def _normalize_store(data: dict[str, Any] | None = None) -> dict[str, Any]:
    store = _default_store()
    if isinstance(data, dict):
        store.update({k: copy.deepcopy(v) for k, v in data.items() if k in {"version", "active_skin", "unlocked", "custom"}})
    unlocked = [str(x) for x in store.get("unlocked", []) if isinstance(x, str)]
    for skin_id in DEFAULT_UNLOCKED:
        if skin_id not in unlocked:
            unlocked.append(skin_id)
    store["unlocked"] = unlocked
    custom = []
    for item in store.get("custom", []):
        if isinstance(item, dict):
            try:
                custom.append(_normalize_skin(item, source="custom"))
            except ValueError:
                continue
    store["custom"] = custom
    if str(store.get("active_skin") or "") not in _skin_map(store):
        store["active_skin"] = DEFAULT_SKIN
    store["version"] = 1
    return store


def load_store() -> dict[str, Any]:
    store = _normalize_store(_read_json(SKINS_FILE))
    if not SKINS_FILE.exists():
        _atomic_write(SKINS_FILE, store)
    return store


def save_store(store: dict[str, Any]) -> dict[str, Any]:
    store = _normalize_store(store)
    _atomic_write(SKINS_FILE, store)
    return store


def _skin_map(store: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    result = {k: copy.deepcopy(v) for k, v in BUILTIN_SKINS.items()}
    if store:
        for item in store.get("custom", []):
            if isinstance(item, dict) and item.get("id"):
                result[str(item["id"])] = copy.deepcopy(item)
    return result


def _with_state(skin: dict[str, Any], store: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(skin)
    out["unlocked"] = str(out.get("id")) in set(store.get("unlocked", []))
    out["active"] = str(out.get("id")) == str(store.get("active_skin"))
    out["rules_effect"] = "none"
    return out


def list_skins() -> dict[str, Any]:
    store = load_store()
    skins = [_with_state(s, store) for s in _skin_map(store).values()]
    skins.sort(key=lambda s: (0 if s.get("source") == "builtin" else 1, str(s.get("name") or s.get("id"))))
    return {"active_skin": store["active_skin"], "unlocked": list(store["unlocked"]), "skins": skins, "count": len(skins)}


def current_skin() -> dict[str, Any]:
    store = load_store()
    skin = _skin_map(store).get(str(store.get("active_skin"))) or BUILTIN_SKINS[DEFAULT_SKIN]
    return _with_state(skin, store)


def set_current_skin(skin_id: str) -> dict[str, Any]:
    skin_id = str(skin_id or "").strip()
    store = load_store()
    skins = _skin_map(store)
    if skin_id not in skins:
        raise KeyError(f"unknown skin: {skin_id}")
    if skin_id not in set(store.get("unlocked", [])):
        raise PermissionError(f"skin locked: {skin_id}")
    store["active_skin"] = skin_id
    save_store(store)
    return _with_state(skins[skin_id], store)


def _normalize_visual(visual: Any) -> dict[str, str]:
    if not isinstance(visual, dict):
        raise ValueError("visual object required")
    allowed = set(next(iter(BUILTIN_SKINS.values()))["visual"].keys())
    base = copy.deepcopy(BUILTIN_SKINS[DEFAULT_SKIN]["visual"])
    for key, value in visual.items():
        if key in allowed and isinstance(value, str) and value.strip():
            base[key] = value.strip()[:240]
    return base


def _normalize_skin(payload: dict[str, Any], source: str = "custom") -> dict[str, Any]:
    skin_id = str(payload.get("id") or "").strip().lower().replace(" ", "-")
    if not _ID_RE.match(skin_id):
        raise ValueError("invalid skin id")
    if skin_id in BUILTIN_SKINS and source == "custom":
        raise ValueError("custom skin id conflicts with builtin skin")
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("name required")
    def str_list(key: str, limit: int = 6) -> list[str]:
        raw = payload.get(key) or []
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list):
            return []
        return [str(x).strip()[:24] for x in raw if str(x).strip()][:limit]
    return {
        "id": skin_id,
        "name": name[:32],
        "source": source,
        "description": str(payload.get("description") or "").strip()[:180],
        "mood": str_list("mood"),
        "suitable_policies": str_list("suitable_policies", 5),
        "suitable_states": str_list("suitable_states", 6),
        "rules_effect": "none",
        "visual": _normalize_visual(payload.get("visual") or {}),
        "created_at": float(payload.get("created_at") or time.time()),
    }


def create_skin(payload: dict[str, Any], unlock: bool = True, activate: bool = False) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("JSON object required")
    if str(payload.get("rules_effect") or "none") != "none":
        raise ValueError("skins cannot modify gameplay rules; rules_effect must be none")
    skin = _normalize_skin(payload, source="custom")
    store = load_store()
    custom = [s for s in store.get("custom", []) if str(s.get("id")) != skin["id"]]
    custom.append(skin)
    store["custom"] = custom
    if unlock and skin["id"] not in store.get("unlocked", []):
        store.setdefault("unlocked", []).append(skin["id"])
    if activate:
        store["active_skin"] = skin["id"]
    save_store(store)
    return _with_state(skin, store)
