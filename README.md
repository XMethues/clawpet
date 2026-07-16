# clawchat-pet

A Hermes Agent plugin that turns agent activity into a persistent cultivation pet experience for ClawChat.

## Features

- Starts and serves the local pet API and bundled web UI
- Starts and manages the Liveware tunnel agent with the plugin lifecycle
- Converts Hermes activity hooks into cultivation progress and event logs
- Supports pets, skins, realms, techniques, artifacts, daily policies, and idle progression
- Registers the bundled `clawchat-pet` skill with Hermes

## Runtime

When Hermes loads the plugin, it ensures that:

1. The pet service is available on `127.0.0.1:54321`
2. The Liveware tunnel agent is running

Runtime state is stored outside this repository under `~/.hermes/clawchat-pet/`.

## Tests

```bash
PYTHONPATH=. python tests/test_liveware_lifecycle.py -v
PYTHONPATH=. python tests/test_xianxia_tool_labels.py -v
```
