# clawchat-pet

A Hermes Agent plugin that turns agent activity into one persistent pet growth journey and projects it through selectable gameplay scenes for ClawChat.

## Features

- Starts and serves the local pet API and bundled web UI
- Starts and manages the Liveware tunnel agent with the plugin lifecycle
- Converts Hermes activity hooks into shared growth progress and structured event facts
- Aggregates parallel tools, approvals, turns, and subagents into one activity display
- Uses the current Petdex entry as pet identity while sharing progress across pets and scenes
- Stores an optional text-only personality independently for each Petdex slug
- Ships xianxia and star-voyage scene adapters over the same settlement rules
- Supports pets, skins, stages, capabilities, assets, daily strategies, and idle progression
- Registers the bundled `clawchat-pet` skill with Hermes

## Runtime

When Hermes loads the plugin, it ensures that:

1. The pet service is available on `127.0.0.1:54321`
2. The Liveware tunnel agent is running

Runtime state is stored outside this repository under `~/.hermes/clawchat-pet/`.
One authoritative runtime owns `save.json`, its lock, and atomic commits. Shared growth, current pet, per-pet personalities, current scene/skin, and per-skin visual overrides live in that one save. Petdex sprite/index files are cache, not product state. Transient activity is memory-only and returns to idle whenever the Hermes plugin process restarts. Hermes hooks call the runtime directly in-process.

## Gameplay scenes

The display-only frontend reads one projected presentation. The bundled skill performs changes through the catalog and command interface:

```text
GET  /presentation
GET  /catalog
POST /command   {"type":"select_scene","scene_id":"star-voyage"}
```

`xianxia` is the default scene and `star-voyage` is the second built-in adapter. A scene owns multiple compatible skins and one default skin. A skin changes only visual tokens; user overrides are stored against that skin. Selecting a scene also selects its default skin.

To add a built-in scene, define another `SceneDefinition` in `clawchat_pet/gameplay.py`, register it in `GameplayScenes`, and add at least one matching skin in `clawchat_pet/skins.py`. A scene supplies stage, meter, strategy, activity, voice, capability, asset, and chronicle labels for fixed shared-growth slots. It cannot settle progress. `PetPresentation` validates the scene/skin relationship and produces the single read model.

## Python environment

Python dependencies are managed with [uv](https://docs.astral.sh/uv/). The
project targets the same Python 3.11 minimum as Hermes Agent.

```bash
uv sync --locked
```

This creates a local `.venv` and installs the locked Pillow dependency used by
the Petdex sprite pipeline.

## Frontend

The complete Vite + React + TypeScript project is in [`frontend/`](frontend/). The generated production bundle is committed under `clawchat_pet/web/` so the plugin works immediately after installation.

```bash
cd frontend
npm ci
npm run dev      # development server with API proxy
npm run build    # rebuilds ../clawchat_pet/web/
```

## Tests

```bash
uv run --locked python -m unittest discover -s tests -v
```
