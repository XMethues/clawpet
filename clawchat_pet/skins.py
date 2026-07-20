"""Immutable skin definitions plus caller-owned visual overrides."""
from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any


_BASE_VISUAL = {
    "bgMain": "linear-gradient(180deg, #0b1d2a 0%, #0a0d18 100%)",
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
}


def _skin(
    skin_id: str,
    scene_id: str,
    name: str,
    description: str,
    visual: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "id": skin_id,
        "scene_id": scene_id,
        "name": name,
        "source": "builtin",
        "description": description,
        "rules_effect": "none",
        "visual": {**_BASE_VISUAL, **visual},
    }


BUILTIN_SKINS: dict[str, dict[str, Any]] = {
    "qingming": _skin(
        "qingming", "xianxia", "青冥道场", "青蓝、清净、稳定的修仙道场。", {}
    ),
    "chiyan": _skin(
        "chiyan", "xianxia", "赤焰道场", "赤红、金橙、烈焰的修仙道场。", {
            "bgMain": "linear-gradient(180deg, #27110d 0%, #100b12 100%)",
            "panel": "rgba(45, 18, 13, 0.84)",
            "panelSoft": "rgba(58, 23, 12, 0.76)",
            "accent": "#ff9b45", "accentSoft": "rgba(255, 155, 69, 0.42)",
            "textMain": "#ffe1c1", "textMuted": "#c89472", "gold": "#ffd36e",
            "border": "rgba(224, 117, 64, 0.50)", "track": "rgba(82, 35, 24, 0.80)",
            "bubbleBg": "rgba(48, 18, 13, 0.88)",
            "bubbleBorder": "rgba(255, 154, 77, 0.42)", "bubbleText": "#ffe3cc",
            "qi": "#ffb347", "demon": "#ff6170", "glow": "rgba(255, 119, 46, 0.20)",
        },
    ),
    "xuanshui": _skin(
        "xuanshui", "xianxia", "玄水道场", "深蓝、水纹、安静的修仙道场。", {
            "bgMain": "linear-gradient(180deg, #071929 0%, #06101d 100%)",
            "panel": "rgba(7, 24, 39, 0.86)", "panelSoft": "rgba(8, 34, 54, 0.76)",
            "accent": "#5fe7dc", "accentSoft": "rgba(95, 231, 220, 0.36)",
            "textMain": "#d4ffff", "textMuted": "#80b8bc", "gold": "#ccebd8",
            "border": "rgba(84, 189, 190, 0.44)", "track": "rgba(22, 61, 77, 0.80)",
            "bubbleBg": "rgba(6, 31, 47, 0.90)",
            "bubbleBorder": "rgba(95, 231, 220, 0.36)", "bubbleText": "#d7ffff",
            "qi": "#5fe7dc", "demon": "#b47cff", "glow": "rgba(95, 231, 220, 0.16)",
        },
    ),
    "xinghai": _skin(
        "xinghai", "star-voyage", "星海舰桥", "深空蓝与冷青色的远征舰桥。", {
            "bgMain": "linear-gradient(180deg, #071228 0%, #050812 100%)",
            "panel": "rgba(8, 19, 42, 0.86)", "panelSoft": "rgba(11, 29, 58, 0.76)",
            "accent": "#68d8ff", "accentSoft": "rgba(104, 216, 255, 0.36)",
            "textMain": "#e1f2ff", "textMuted": "#89a9c7", "gold": "#e3dd9a",
            "border": "rgba(91, 146, 213, 0.44)", "track": "rgba(23, 47, 81, 0.80)",
            "bubbleBg": "rgba(7, 22, 45, 0.90)",
            "bubbleBorder": "rgba(104, 216, 255, 0.36)", "bubbleText": "#e1f6ff",
            "qi": "#68d8ff", "demon": "#ff718c", "glow": "rgba(80, 154, 255, 0.18)",
        },
    ),
    "chenhui": _skin(
        "chenhui", "star-voyage", "晨辉舰桥", "暖金晨辉中的轻型探索舰桥。", {
            "bgMain": "linear-gradient(180deg, #251c27 0%, #0e101b 100%)",
            "panel": "rgba(37, 28, 39, 0.86)", "panelSoft": "rgba(54, 39, 48, 0.76)",
            "accent": "#ffca72", "accentSoft": "rgba(255, 202, 114, 0.38)",
            "textMain": "#fff0d5", "textMuted": "#c2a88b", "gold": "#ffe08b",
            "border": "rgba(213, 158, 99, 0.46)", "track": "rgba(76, 53, 57, 0.80)",
            "bubbleBg": "rgba(43, 30, 39, 0.90)",
            "bubbleBorder": "rgba(255, 202, 114, 0.38)", "bubbleText": "#fff1d8",
            "qi": "#ffca72", "demon": "#df708a", "glow": "rgba(255, 181, 91, 0.18)",
        },
    ),
}

DEFAULT_SKIN = "qingming"


class SkinCatalog:
    def __init__(self, definitions: Mapping[str, Mapping[str, Any]] = BUILTIN_SKINS):
        self._definitions = {
            str(skin_id): copy.deepcopy(dict(item))
            for skin_id, item in definitions.items()
        }

    def get(self, skin_id: str) -> dict[str, Any]:
        try:
            return copy.deepcopy(self._definitions[skin_id])
        except KeyError:
            raise KeyError(f"unknown skin: {skin_id}") from None

    def list(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(item) for item in self._definitions.values()]

    def for_scene(self, scene_id: str) -> tuple[str, ...]:
        return tuple(
            skin_id for skin_id, item in self._definitions.items()
            if item["scene_id"] == scene_id
        )

    def resolve(self, skin_id: str, override: Any = None) -> dict[str, Any]:
        skin = self.get(skin_id)
        if isinstance(override, Mapping):
            skin["visual"].update(copy.deepcopy(dict(override)))
        return skin

    def normalize_override(self, skin_id: str, visual: Any) -> dict[str, str]:
        skin = self.get(skin_id)
        if not isinstance(visual, Mapping) or not visual:
            raise ValueError("visual must be a non-empty object")
        unsupported = set(visual) - set(skin["visual"])
        if unsupported:
            raise ValueError(
                f"unsupported visual fields: {', '.join(sorted(unsupported))}"
            )
        normalized = {}
        for key, value in visual.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"visual.{key} must be a non-empty string")
            normalized[str(key)] = value.strip()[:240]
        return normalized
