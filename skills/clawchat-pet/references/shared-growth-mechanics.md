# Shared Growth Mechanics Notes

Use this reference when explaining the shared progression curve, trials, and risk. Shared growth stores only neutral identifiers and values. The default xianxia scene supplies the themed labels shown below; another gameplay scene may project the same snapshot differently.

## Stage Path

Shared growth has 28 ordered stages. The xianxia scene presents them as:

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

The gate is followed by two trial stages and then four ordinary stages.

## Neutral Dimensions

```text
primary        progress toward the next stage
risk           backlash and regression pressure
stability      foundation strength
insight        higher-stage readiness
strain         overuse pressure
fortune        accumulated opportunity
```

The xianxia scene presents these as 灵气、心魔、道心、悟性、疲劳 and 机缘. Scene labels are presentation only.

## Trial Rule

A failure raises pressure and risk but never advances a trial. A successful work event advances a ready trial. Ordinary ready stages advance after a durable growth event.

## Regression Rule

Regression is deliberately rare. It requires all of the following:

```text
idle for at least 5 days
risk above the current stage tolerance
stability below the current stage requirement
not at the first stage
not inside a trial stage
```

The 1-2-3-4-5 day idle milestones settle lazily and only once per idle streak. The selected strategy weights their effects.

## Delivery and History

The Hermes activity module maps raw tool names to stable capability IDs before it creates normalized growth events. Those events are applied immediately and deduplicated by shared growth. If the runtime's atomic commit fails, the transaction object, raw-callback correlation changes, and transient activity change are discarded. The save contains the current snapshot plus bounded recent stable facts; it is not an event-sourced replay log.
