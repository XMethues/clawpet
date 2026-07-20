"""Petdex-backed pet identity and per-pet personality policy."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Iterable, Mapping


DEFAULT_PET_ID = "yinyue-2"
PERSONALITY_EVENTS = {
    "idle", "review", "run", "wave", "failed", "waiting", "unknown", "subagent"
}


class PetModule:
    """Hide Petdex/cache details behind pet-domain operations.

    Durable identity and personality values live in the root runtime save passed
    to these methods.  The Petdex provider is only an external catalog/cache.
    """

    def __init__(self, *, catalog: Iterable[Mapping[str, Any]] | None, provider=None):
        self._fixed_catalog = (
            {
                str(item["slug"]): self._normalize_pet(item)
                for item in catalog
            }
            if catalog is not None
            else None
        )
        self._provider = provider
        self._catalog_cache: dict[str, dict[str, Any]] | None = None
        if self._fixed_catalog is not None and DEFAULT_PET_ID not in self._fixed_catalog:
            raise ValueError(f"pet catalog must contain {DEFAULT_PET_ID!r}")

    @staticmethod
    def _normalize_pet(raw: Any) -> dict[str, Any]:
        item = raw if isinstance(raw, Mapping) else raw.to_dict()
        pet = copy.deepcopy(dict(item))
        slug = str(pet.get("slug") or "").strip()
        if not slug:
            raise ValueError("pet slug is required")
        pet["slug"] = slug
        pet["spriteUrl"] = f"/assets/pets/{slug}.png"
        return pet

    def catalog(self) -> dict[str, dict[str, Any]]:
        if self._fixed_catalog is not None:
            return copy.deepcopy(self._fixed_catalog)
        if self._catalog_cache is not None:
            return copy.deepcopy(self._catalog_cache)
        provider = self._provider
        if provider is None:
            from .services import petdex as provider
        try:
            pets = {
                str(item["slug"]): item
                for item in (self._normalize_pet(raw) for raw in provider.list_pets(force=False))
            }
        except Exception:
            pets = {}
        pets.setdefault(DEFAULT_PET_ID, {
            "slug": DEFAULT_PET_ID,
            "displayName": "Yinyue",
            "description": "",
            "source": "petdex",
            "assetKind": "sprite",
            "cached": False,
            "spriteUrl": f"/assets/pets/{DEFAULT_PET_ID}.png",
            "cellWidth": 192,
            "cellHeight": 208,
        })
        self._catalog_cache = pets
        return copy.deepcopy(pets)

    def current(self, pet_state: Mapping[str, Any]) -> dict[str, Any]:
        slug = str(pet_state.get("current") or DEFAULT_PET_ID)
        try:
            pet = self.catalog()[slug]
        except KeyError:
            raise RuntimeError(f"saved pet is unavailable: {slug}") from None
        personality = self.personality(pet_state, slug)
        pet["personality_state"] = personality["state"]
        pet["prompt_personality"] = personality["state"] == "undecided"
        return pet

    def select(self, pet_state: dict[str, Any], slug: str) -> None:
        slug = str(slug or "").strip()
        catalog = self.catalog()
        if slug not in catalog:
            raise KeyError(f"unknown Petdex pet: {slug}")
        if self._fixed_catalog is None:
            provider = self._provider
            if provider is None:
                from .services import petdex as provider
            cached = provider.ensure_cached(slug)
            if cached is not None:
                assert self._catalog_cache is not None
                self._catalog_cache[slug] = self._normalize_pet(cached)
        pet_state["current"] = slug

    def personality(self, pet_state: Mapping[str, Any], slug: str) -> dict[str, Any]:
        if slug not in self.catalog():
            raise KeyError(f"unknown Petdex pet: {slug}")
        stored = (pet_state.get("personalities") or {}).get(slug)
        if not isinstance(stored, Mapping):
            return {"slug": slug, "state": "undecided", "profile": None}
        return {"slug": slug, **copy.deepcopy(dict(stored))}

    def configure_personality(
        self, pet_state: dict[str, Any], slug: str, profile: Any
    ) -> None:
        if slug not in self.catalog():
            raise KeyError(f"unknown Petdex pet: {slug}")
        if not isinstance(profile, Mapping):
            raise ValueError("profile must be an object")
        if set(profile) - {"style", "lines"}:
            raise ValueError("profile contains unsupported fields")
        style = profile.get("style")
        lines = profile.get("lines")
        if not isinstance(style, str) or not style.strip() or len(style) > 200:
            raise ValueError("style must be 1-200 characters")
        if not isinstance(lines, Mapping) or not lines or set(lines) - PERSONALITY_EVENTS:
            raise ValueError("lines contain unsupported event groups")
        normalized_lines: dict[str, list[str]] = {}
        for event, values in lines.items():
            if not isinstance(values, list) or not 1 <= len(values) <= 20:
                raise ValueError("each line group must contain 1-20 lines")
            if any(
                not isinstance(line, str) or not line.strip() or len(line) > 200
                for line in values
            ):
                raise ValueError("personality lines must be 1-200 characters")
            normalized_lines[str(event)] = [line.strip() for line in values]
        pet_state.setdefault("personalities", {})[slug] = {
            "state": "configured",
            "profile": {"style": style.strip(), "lines": normalized_lines},
        }

    def set_neutral_personality(self, pet_state: dict[str, Any], slug: str) -> None:
        if slug not in self.catalog():
            raise KeyError(f"unknown Petdex pet: {slug}")
        pet_state.setdefault("personalities", {})[slug] = {
            "state": "neutral", "profile": None
        }

    def reset_personality(self, pet_state: dict[str, Any], slug: str) -> None:
        if slug not in self.catalog():
            raise KeyError(f"unknown Petdex pet: {slug}")
        pet_state.setdefault("personalities", {}).pop(slug, None)

    def sprite_path(self, slug: str) -> Path:
        slug = str(slug or "").strip()
        catalog = self.catalog()
        if slug not in catalog:
            raise KeyError(f"unknown Petdex pet: {slug}")
        fixed_path = catalog[slug].get("spritePath")
        if fixed_path:
            path = Path(str(fixed_path))
            if not path.is_file():
                raise FileNotFoundError(str(path))
            return path
        provider = self._provider
        if provider is None:
            from .services import petdex as provider
        return Path(provider.sprite_path(slug))
