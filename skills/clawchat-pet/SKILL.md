---
name: clawchat-pet
description: "用于查询或修改 ClawPet 宠物、玩法场景、皮肤、人格和成长策略."
version: 0.5.3
author: clawchat-pet
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [hermes, plugin, petdex, scenes, skins]
---

# clawchat-pet

Use the plugin-owned local HTTP interface. The web UI is display-only; perform all owner-requested changes through this skill.

```text
GET  /presentation
GET  /catalog
POST /command
```

`GET /catalog` returns the active pet, scene, and skin plus all available pets, scenes, and skins. Resolve names to IDs from this response before sending a command. A successful command returns the complete updated presentation.

## Commands

```json
{"type":"select_pet","pet_id":"boba"}
{"type":"select_scene","scene_id":"star-voyage"}
{"type":"select_skin","skin_id":"chenhui"}
{"type":"select_strategy","strategy_id":"advance"}
{"type":"customize_skin","skin_id":"chenhui","visual":{"accent":"#ffcc77"}}
{"type":"customize_skin","skin_id":"chenhui","visual":{"backgroundImage":"url('https://example.com/background.webp')"}}
{"type":"reset_skin","skin_id":"chenhui"}
{"type":"set_neutral_personality","pet_id":"boba"}
{"type":"reset_personality","pet_id":"boba"}
```

To configure personality, generate a text-only profile and send:

```json
{
  "type": "configure_personality",
  "pet_id": "boba",
  "profile": {
    "style": "brief description of the speaking style",
    "lines": {
      "idle": ["one or more text-bubble lines"],
      "review": ["..."],
      "run": ["..."],
      "wave": ["..."],
      "failed": ["..."],
      "waiting": ["..."]
    }
  }
}
```

Supported line groups are `idle`, `review`, `run`, `wave`, `failed`, `waiting`, `unknown`, and `subagent`. Styles and individual lines are limited to 200 characters.

## Invariants

- External publication is plugin-owned and always uses the fixed Liveware and ClawChat name `ClawPet`; do not create per-pet publication apps.
- `yinyue-2` is the default Petdex slug, not a special identity. Confirm changes using `displayName`.
- Pet switching never resets shared growth, scene, or skin.
- Personality is per pet and affects only text-bubble utterances. If `prompt_personality` is true after switching, ask once whether to configure it; neutral suppresses future prompts and reset makes it undecided again.
- A gameplay scene interprets stable shared-growth facts. It never owns formulas or progress.
- Each skin belongs to one scene and changes visuals only. Selecting a scene selects that scene's default skin. Skin overrides are stored per skin until reset.
- Skin visual overrides are runtime data. `backgroundImage` accepts a CSS image value such as `url('https://...')`; the polling frontend applies it without a rebuild.
- Local custom backgrounds belong in the active Hermes runtime directory at `clawchat-pet/backgrounds/<filename>`, not inside the plugin checkout. Reference them as `url('/assets/backgrounds/<filename>?v=<version>')`; use a new version query when replacing a file at the same path. Supported formats are AVIF, GIF, JPEG, PNG, SVG, and WebP.
- Design backgrounds for a portrait 430:800 viewport. Prefer 860×1600 WebP for raster art (1080×1920 is also suitable), keep the central 55% low-contrast for the pet and speech bubble, and target no more than 1 MB for mobile delivery. Backgrounds use centered `cover` cropping.
- Strategies use stable IDs: `balanced`, `advance`, `stabilize`, `learn`, and `recover`.
- Approval denial, approval timeout, interrupted turns, subagent lifecycle, and unknown tool results are neutral. Only actual tool failures create failure growth events.
