from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PIL import Image

HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
CACHE_ROOT = HERMES_HOME / "clawchat-pet" / "cache"
PETS_CACHE = CACHE_ROOT / "pets"
INDEX_FILE = CACHE_ROOT / "petdex-index.json"
PETDEX_URL = "https://petdex.dev/"
UA = "Mozilla/5.0 (Hermes clawchat-pet)"

STATE_ROWS = {
    "idle": 0,
    "run": 1,
    "run_left": 2,
    "wave": 3,
    "jump": 4,
    "failed": 5,
    "waiting": 6,
    "running": 7,
    "review": 8,
}


@dataclass
class PetInfo:
    slug: str
    displayName: str
    description: str = ""
    source: str = "petdex"
    assetUrl: str | None = None
    assetKind: str = "sprite"  # sprite | preview | local
    cached: bool = False
    spriteUrl: str | None = None
    width: int | None = None
    height: int | None = None
    cellWidth: int = 192
    cellHeight: int = 208
    rows: int | None = None
    columns: int | None = None
    frames: dict[str, int] | None = None
    updatedAt: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _json_response(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _slug_title(slug: str) -> str:
    base = re.sub(r"-[0-9a-f]{8,}$", "", slug)
    return " ".join(part.capitalize() for part in base.replace("_", "-").split("-") if part) or slug


def _fetch_text(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _download(url: str, dest: Path, timeout: int = 40) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, dest)


def _scan_sprite(png_path: Path) -> dict[str, Any]:
    img = Image.open(png_path).convert("RGBA")
    width, height = img.size
    cell_w, cell_h = 192, 208
    columns = max(1, width // cell_w)
    rows = max(1, height // cell_h)
    frames_by_row: list[int] = []
    for r in range(rows):
        count = 0
        for c in range(columns):
            box = (c * cell_w, r * cell_h, min((c + 1) * cell_w, width), min((r + 1) * cell_h, height))
            crop = img.crop(box).convert("RGBA")
            alpha = crop.getchannel("A")
            total = crop.size[0] * crop.size[1]
            transparent = sum(1 for a in alpha.getdata() if a < 10) / max(1, total)
            if transparent < 0.90:
                count += 1
        frames_by_row.append(max(1, count))

    frames: dict[str, int] = {}
    if rows >= 9:
        for state, row in STATE_ROWS.items():
            if row < len(frames_by_row):
                frames[state] = frames_by_row[row]
        # UI aliases.
        frames["run"] = frames.get("run", 1)
        frames["review"] = frames.get("review", frames.get("running", 1))
    else:
        first = frames_by_row[0] if frames_by_row else columns
        for state in ["idle", "run", "wave", "jump", "failed", "waiting", "review"]:
            frames[state] = first

    return {
        "width": width,
        "height": height,
        "cellWidth": cell_w,
        "cellHeight": cell_h,
        "columns": columns,
        "rows": rows,
        "framesByRow": frames_by_row,
        "frames": frames,
    }


def _write_meta(slug_dir: Path, info: PetInfo) -> None:
    slug_dir.mkdir(parents=True, exist_ok=True)
    (slug_dir / "meta.json").write_text(_json_response(info.to_dict()), encoding="utf-8")


def _read_meta(slug: str) -> PetInfo | None:
    path = PETS_CACHE / slug / "meta.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        info = PetInfo(**{
            key: value for key, value in data.items()
            if key in PetInfo.__dataclass_fields__
        })
        info.spriteUrl = f"/assets/pets/{slug}.png"
        return info
    except Exception:
        return None


def _local_pet(slug: str, pet_dir: Path) -> PetInfo | None:
    pet_json = pet_dir / "pet.json"
    if not pet_json.exists():
        return None
    try:
        data = json.loads(pet_json.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    src = pet_dir / data.get("spritesheetPath", "spritesheet.webp")
    if not src.exists():
        return None
    info = PetInfo(
        slug=slug,
        displayName=data.get("displayName") or data.get("name") or _slug_title(slug),
        description=data.get("description", ""),
        source="local",
        assetUrl=str(src),
        assetKind="local",
        cached=False,
    )
    return info


def local_pets() -> list[PetInfo]:
    root = HERMES_HOME / "pets"
    out: list[PetInfo] = []
    if root.exists():
        for d in sorted(p for p in root.iterdir() if p.is_dir()):
            info = _local_pet(d.name, d)
            if info:
                meta = _read_meta(info.slug)
                if meta:
                    info.cached = True
                    info.spriteUrl = meta.spriteUrl
                    info.width = meta.width
                    info.height = meta.height
                    info.rows = meta.rows
                    info.columns = meta.columns
                    info.frames = meta.frames
                out.append(info)
    return out


def _extract_petdex_index(html: str) -> list[PetInfo]:
    assets = sorted(set(re.findall(r"https://assets\.petdex\.dev/[^\\\"'<>\s&)]+", html)))
    items: dict[str, PetInfo] = {}
    for url in assets:
        if not url.endswith(("sprite.webp", "spritesheet.webp", "preview.webp")):
            continue
        parsed = urlparse(url)
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) < 2:
            continue
        # /pets/<slug>/sprite.webp or /curated/<slug>/spritesheet.webp
        slug = parts[-2]
        kind = "preview" if parts[-1] == "preview.webp" else "sprite"
        # Prefer full sprite/spritesheet over preview.
        existing = items.get(slug)
        if existing and existing.assetKind == "sprite" and kind == "preview":
            continue
        meta = _read_meta(slug)
        item = PetInfo(
            slug=slug,
            displayName=_slug_title(slug),
            source="petdex",
            assetUrl=url,
            assetKind=kind,
            cached=bool(meta),
            spriteUrl=(meta.spriteUrl if meta else None),
            width=(meta.width if meta else None),
            height=(meta.height if meta else None),
            rows=(meta.rows if meta else None),
            columns=(meta.columns if meta else None),
            frames=(meta.frames if meta else None),
        )
        items[slug] = item
    return sorted(items.values(), key=lambda p: (p.assetKind != "sprite", p.displayName.lower()))


def refresh_index(force: bool = False) -> list[PetInfo]:
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    if not force and INDEX_FILE.exists():
        try:
            data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
            if time.time() - float(data.get("ts", 0)) < 24 * 3600:
                remote = [PetInfo(**x) for x in data.get("pets", [])]
                return merge_with_local(remote)
        except Exception:
            pass
    html = _fetch_text(PETDEX_URL)
    remote = _extract_petdex_index(html)
    INDEX_FILE.write_text(
        _json_response({"ts": time.time(), "source": PETDEX_URL, "pets": [p.to_dict() for p in remote]}),
        encoding="utf-8",
    )
    return merge_with_local(remote)


def merge_with_local(remote: list[PetInfo]) -> list[PetInfo]:
    by_slug: dict[str, PetInfo] = {p.slug: p for p in remote}
    for lp in local_pets():
        # Local copy wins for same slug because it works offline and may be private/custom.
        by_slug[lp.slug] = lp
    # Ensure current yinyue fallback is first-ish by natural display sort still ok.
    return sorted(by_slug.values(), key=lambda p: (p.slug != "yinyue-2", p.source != "local", p.displayName.lower()))


def list_pets(force: bool = False) -> list[PetInfo]:
    try:
        return refresh_index(force=force)
    except Exception:
        cached: list[PetInfo] = []
        if INDEX_FILE.exists():
            try:
                data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
                cached = [PetInfo(**x) for x in data.get("pets", [])]
            except Exception:
                cached = []
        return merge_with_local(cached)


def get_pet(slug: str) -> PetInfo | None:
    meta = _read_meta(slug)
    if meta:
        return meta
    for p in list_pets(force=False):
        if p.slug == slug:
            return p
    return None


def ensure_cached(slug: str) -> PetInfo:
    pet = get_pet(slug)
    if pet is None:
        raise KeyError(f"unknown pet: {slug}")
    cached = _read_meta(slug)
    if cached and (PETS_CACHE / slug / "sprite.png").exists():
        return cached

    slug_dir = PETS_CACHE / slug
    slug_dir.mkdir(parents=True, exist_ok=True)
    source = slug_dir / "source.webp"
    png = slug_dir / "sprite.png"

    if pet.source == "local" and pet.assetUrl:
        src_path = Path(pet.assetUrl)
        if not src_path.exists():
            raise FileNotFoundError(str(src_path))
        shutil_src = src_path
        Image.open(shutil_src).convert("RGBA").save(png, "PNG")
        source.write_bytes(src_path.read_bytes())
    elif pet.assetUrl:
        _download(pet.assetUrl, source)
        Image.open(source).convert("RGBA").save(png, "PNG")
    else:
        raise ValueError(f"pet {slug} has no asset")

    scan = _scan_sprite(png)
    info = PetInfo(
        slug=pet.slug,
        displayName=pet.displayName,
        description=pet.description,
        source=pet.source,
        assetUrl=pet.assetUrl,
        assetKind=pet.assetKind,
        cached=True,
        spriteUrl=f"/assets/pets/{pet.slug}.png",
        width=scan["width"],
        height=scan["height"],
        cellWidth=scan["cellWidth"],
        cellHeight=scan["cellHeight"],
        rows=scan["rows"],
        columns=scan["columns"],
        frames=scan["frames"],
        updatedAt=time.time(),
    )
    _write_meta(slug_dir, info)
    return info


def sprite_path(slug: str) -> Path:
    info = ensure_cached(slug)
    p = PETS_CACHE / info.slug / "sprite.png"
    if not p.exists():
        raise FileNotFoundError(str(p))
    return p
