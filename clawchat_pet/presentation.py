"""Coherent scene + skin projection of shared pet growth."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .gameplay import DEFAULT_SCENE_ID, GameplayScenes
from .skins import SkinCatalog


class PetPresentation:
    """Own the scene/skin relationship and produce one frontend read model."""

    def __init__(
        self,
        scenes: GameplayScenes | None = None,
        skins: SkinCatalog | None = None,
    ) -> None:
        self._scenes = scenes or GameplayScenes()
        self._skins = skins or SkinCatalog()
        for summary in self._scenes.catalog(DEFAULT_SCENE_ID)["scenes"]:
            scene_id = str(summary["id"])
            actual = self._skins.for_scene(scene_id)
            declared = tuple(summary["skin_ids"])
            if set(actual) != set(declared):
                raise ValueError(f"scene {scene_id!r} and its skin catalog disagree")
            if summary["default_skin_id"] not in actual:
                raise ValueError(f"scene {scene_id!r} has an invalid default skin")

    def new_selection(self) -> dict[str, Any]:
        scene = self._scenes.get(DEFAULT_SCENE_ID)
        return {
            "scene_id": DEFAULT_SCENE_ID,
            "skin_id": scene.default_skin_id,
            "skin_overrides": {},
        }

    def project(
        self,
        selection: Mapping[str, Any],
        cultivation: Mapping[str, Any],
        activity: Mapping[str, Any],
        pet: Mapping[str, Any],
        personality: Mapping[str, Any],
    ) -> dict[str, Any]:
        result = self._scenes.project(
            str(selection["scene_id"]), cultivation, activity, pet, personality
        )
        skin_id = str(selection["skin_id"])
        override = (selection.get("skin_overrides") or {}).get(skin_id)
        result["skin"] = self._skins.resolve(skin_id, override)
        return result

    def catalog(self, selection: Mapping[str, Any]) -> dict[str, Any]:
        scene_id = str(selection["scene_id"])
        skin_id = str(selection["skin_id"])
        scenes = self._scenes.catalog(scene_id)["scenes"]
        skins = self._skins.list()
        for skin in skins:
            skin["active"] = skin["id"] == skin_id
        return {"scenes": scenes, "skins": skins}

    def apply_command(
        self,
        selection: dict[str, Any],
        command_type: str,
        command: Mapping[str, Any],
    ) -> bool:
        if command_type == "select_scene":
            scene_id = self._required_text(command, "scene_id")
            scene = self._scenes.get(scene_id)
            selection["scene_id"] = scene_id
            selection["skin_id"] = scene.default_skin_id
        elif command_type == "select_skin":
            skin_id = self._required_text(command, "skin_id")
            skin = self._skins.get(skin_id)
            if skin["scene_id"] != selection["scene_id"]:
                raise ValueError(
                    f"skin {skin_id!r} does not belong to scene "
                    f"{selection['scene_id']!r}"
                )
            selection["skin_id"] = skin_id
        elif command_type == "customize_skin":
            skin_id = self._required_text(command, "skin_id")
            normalized = self._skins.normalize_override(skin_id, command.get("visual"))
            overrides = selection.setdefault("skin_overrides", {})
            overrides.setdefault(skin_id, {}).update(normalized)
        elif command_type == "reset_skin":
            skin_id = self._required_text(command, "skin_id")
            self._skins.get(skin_id)
            selection.setdefault("skin_overrides", {}).pop(skin_id, None)
        else:
            return False
        return True

    @staticmethod
    def _required_text(command: Mapping[str, Any], key: str) -> str:
        value = command.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must be a non-empty string")
        return value.strip()
