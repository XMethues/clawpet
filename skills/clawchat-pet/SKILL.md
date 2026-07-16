---
name: clawchat-pet
description: "Use when chatting about 银月道场 / clawchat-pet: pet switching, cultivation stats, realm progression, daily cultivation policy, idle/dormancy rules, and gameplay tuning."
version: 0.2.0
author: clawchat-pet
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [hermes, plugin, petdex, xianxia]
---

# 银月道场 / clawchat-pet

## Overview

`clawchat-pet` is the 银月道场 game layer for Hermes. It turns Hermes activity into a small cultivation pet experience: 银月 gains qi, faces heart demons, rests, breaks through realms, and speaks through the liveware page.

Use this skill when the owner asks about:

- 银月道场 / clawchat-pet
- switching pets or restoring 银月
- cultivation stats, realm, qi, heart demon, dao heart, comprehension, fatigue, fate
- daily cultivation policy: 入定 / 冲关 / 淬心 / 悟道 / 调息
- idle/dormancy rules
- gameplay direction and tuning

## Current Gameplay Loop

```text
Hermes activity
  -> cultivation event
  -> stats change
  -> possible realm progress or breakthrough
  -> 银月 voice / log updates
  -> liveware display refreshes
```

Typical event effects:

```text
thinking / review      -> qi + comprehension, slight fatigue
using tools / run      -> fatigue + fate, small technique growth
successful tool / wave -> qi + technique/artifact growth, possible recovery
failed tool / failed   -> heart demon + fatigue + pressure
waiting / approval     -> fatigue + small dao heart
insight / jump         -> qi + fate + comprehension
```

## Realm Path

Current path has 28 stages:

```text
炼气1-9层
筑基初期 / 中期 / 后期 / 圆满
金丹初期 / 中期 / 后期 / 圆满
元婴初期 / 中期 / 后期 / 圆满
化神门槛
化神·雷劫试炼
化神·元神试炼
化神初期 / 中期 / 后期 / 圆满
```

Breakthrough depends on enough qi plus stable supporting stats. High heart demon, low dao heart, or high fatigue can block or worsen breakthrough attempts.

Trial stages such as 雷劫 and 元神试炼 should feel special: failure increases pressure, while success or insight can resolve the trial.

## Core Stats

```text
qi / 灵气          progress toward the next realm
heart_demon / 心魔 breakthrough risk and regression pressure
dao_heart / 道心  stability and breakthrough foundation
comprehension / 悟性 insight and higher-realm readiness
fatigue / 疲劳    overuse pressure; too high makes risk worse
fate / 气运       luck, opportunities, and lucky recovery
```

## Daily Policy

Policy is a strategic direction, not a button-game action.

```text
入定: default and stable; lower failure backlash and lighter idle loss
冲关: aggressive; higher successful qi gain, heavier failure and idle backlash
淬心: defensive; suppresses heart demon and strengthens recovery after failures
悟道: insight-focused; more comprehension from thinking/insight, slightly lower qi
调息: recovery-focused; stronger fatigue recovery, conservative gains
```

Natural-language mapping:

```text
稳一点 / 默认 / 今天不用你 / 挂着 -> 入定
冲 / 冲关 / 今天冲一把 / 加速 -> 冲关
压心魔 / 心魔高 / 稳心 / 保道心 -> 淬心
研究 / 推演 / 悟性 / 多想想 -> 悟道
休息 / 累了 / 降疲劳 / 恢复状态 -> 调息
```

Recommendation rules:

```text
heart demon high or recent failures -> recommend 淬心
fatigue high -> recommend 调息
low heart demon + low fatigue + near breakthrough -> recommend 冲关
planning/research-heavy day -> recommend 悟道
owner leaving or unclear use today -> recommend 入定
```

If the owner is ambiguous, ask once instead of guessing. When setting a policy, reply briefly and mention the risk profile, e.g. “已切冲关：成功灵气更高，失败反噬也更重。”

## Idle / Dormancy Rules

Use the owner-approved 1-2-3-4-5 day scale:

```text
1 day idle  -> 气机散逸: slight qi leak, fatigue recovers
2 days idle -> 心魔微起: more qi leak, heart demon rises slightly, dao heart dips slightly
3 days idle -> 道基松动: qi/dao heart pressure and heart demon rises
4 days idle -> 散逸加重: heavier qi leak, slight comprehension loss, heart demon rises
5+ days idle + bad state -> possible one-step regression
```

Regression should stay rare and requires all of:

```text
idle at least 5 days
heart demon above current-realm tolerance
dao heart below current-realm need
not already at 炼气1层
not inside 雷劫/元神试炼
```

Each idle milestone should apply once per idle streak. Any non-idle Hermes activity resets the streak to active.

## Pet Switching

Pet switching belongs in conversation: the owner asks, the agent interprets the desired pet, and confirms the result.

Default pet:

```text
yinyue-2 / 银月
```

Good known pets:

```text
yinyue-2
han-li-flying-sword
boba
doraemon-58b12a5012e0
eve-743f1e0e6b0d
mallow-e2413d735bce
noir-webling
wangcai-4745956f417b
```

Prefer full sprite pets over preview-only pets when possible. Preview-only pets may reuse the same animation for all states.
