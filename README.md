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
Transient activity is memory-only and returns to idle whenever the Hermes plugin process restarts. Hook delivery uses the versioned `POST /api/v1/events` endpoint; failed delivery is logged and dropped without replay.

Growth remains in `cultivation.json` for compatibility. The selected gameplay scene is stored separately in `presentation.json`, so changing scenes never rewrites or replays growth.

## Gameplay scenes

The generic frontend reads one projected experience view:

```text
GET  /api/v1/experience
GET  /api/v1/scenes
GET  /api/v1/scenes/current
POST /api/v1/scenes/current   {"id":"star-voyage"}
```

`xianxia` is the default scene and `star-voyage` is the second built-in adapter. Existing `/cultivation`, `/state`, and `/voice` routes remain available as compatibility interfaces.

To add a built-in scene, define another `SceneDefinition` in `clawchat_pet/gameplay.py` and register it in the default `GameplayScenes` tuple. A scene supplies all stage, meter, strategy, activity, voice, capability, asset, and chronicle labels for the fixed shared-growth slots. It must not receive a settlement callback or return progress deltas; gameplay formulas remain exclusively in `simulator.py`. Add the new adapter together with projection tests that compare its meter values and stage index against `xianxia` for the same saved progress.

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
