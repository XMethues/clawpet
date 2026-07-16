# Simulator Mechanics Notes

Use this reference when explaining or tuning realm progression, trials, and risk.

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

`化神门槛` is not a hard cap. It leads into trial stages and then normal 化神 phases.

## Trial Rule

Trial stages should feel different from ordinary realms.

```text
failed event -> increases pressure / heart demon; does not advance the trial
wave event   -> may resolve the trial if requirements are met
jump event   -> may resolve the trial if requirements are met, with insight flavor
```

## Stat Roles

```text
qi            progress toward the next realm
heart demon   risk, backlash, and regression pressure
dao heart     stability and foundation
comprehension insight and higher-realm readiness
fatigue       overuse pressure
fate          luck and opportunity
```

## Regression Rule

Regression should be rare. It should only happen after sustained dormancy and bad state:

```text
idle at least 5 days
heart demon above current-realm tolerance
dao heart below current-realm need
not at 炼气1层
not inside 雷劫/元神试炼
```

The feel should be: neglect creates pressure, but the game does not punish normal short absences.

## Event Delivery Rule

Cultivation events are immediate. If the local game service is briefly unavailable, that event is skipped rather than queued for later replay. This keeps the game simple and avoids delayed surprise jumps.
