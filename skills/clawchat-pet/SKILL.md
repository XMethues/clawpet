---
name: clawchat-pet
description: "Use for clawchat-pet pet switching, Petdex identity, per-pet personality, cultivation progress, policy, and gameplay tuning."
version: 0.3.0
author: clawchat-pet
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [hermes, plugin, petdex, xianxia]
---

# clawchat-pet

`clawchat-pet` turns Hermes activity into a shared cultivation journey presented by the currently selected Petdex pet. Pet identity and personality may change; cultivation progress does not.

## Runtime interface

Use the plugin-owned local HTTP API:

```text
GET  /api/v1/pets
GET  /api/v1/pets/current
POST /api/v1/pets/current                  {"slug":"boba"}
GET  /api/v1/pets/{slug}/personality
POST /api/v1/pets/{slug}/personality
GET  /cultivation
GET  /state
GET  /voice
```

The default Petdex slug is `yinyue-2`. Treat it only as the default/fallback identifier; use the Petdex `displayName` in replies.

## Pet switching conversation

When the owner asks to switch pets:

1. Resolve the requested Petdex slug, asking once if ambiguous.
2. POST `/api/v1/pets/current` with that slug.
3. Confirm using the returned pet `displayName`.
4. Read `personality_state` and `prompt_personality` from the response.
5. If `prompt_personality` is true, ask once whether to create a personality.
6. If false, do not prompt during ordinary switching.

Switching never resets or copies cultivation progress.

## Personality workflow

Personality is stored per Petdex slug and only affects text-bubble utterances.

States:

```text
undecided  no choice recorded; switching requests the one-time prompt
neutral    owner declined or neutralized; do not prompt again
configured a validated style and event line pools are active
```

If the owner accepts creation, generate a profile and submit:

```json
{
  "action": "configure",
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

POST it to `/api/v1/pets/{slug}/personality`. Keep each style or line within 200 characters. Supported line groups are `idle`, `review`, `run`, `wave`, `failed`, `waiting`, `unknown`, and `subagent`.

If the owner declines, send `{"action":"neutral"}`. This records the choice and suppresses future automatic prompts. Explicit later requests may use:

```text
configure  create or replace the profile
neutral    use neutral utterances without prompting
reset      return to undecided and allow a future prompt
```

Never change cultivation stats, policies, rewards, penalties, or progress while editing personality.

## Cultivation model

Hermes activities produce one-time cultivation events and a separate aggregate activity display. Success may reward progress, actual tool failure may penalize it, and unknown results are neutral. Approval denial, approval timeout, interrupted turns, and subagent lifecycle events are neutral.

Activity priority:

```text
候旨 > direct tool / 历练 > 分神化身 > recent result > 推演 > 入定
```

Core stats are 灵气、心魔、道心、悟性、疲劳、气运. The daily policies are 入定、冲关、淬心、悟道、调息. Ask once when policy intent is ambiguous; do not create scheduled prompts unless explicitly requested.

See the bundled references for event delivery, policy guidance, and simulator mechanics.
