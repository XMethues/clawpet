# Policy and Chat Interaction Notes

Use this reference when interpreting owner language about 银月’s daily cultivation direction.

## Layering Rule

Keep the experience simple:

```text
game rules = what changes in the world
skill interpretation = how the agent maps owner language to direction
schedule = only when the owner explicitly asks for proactive prompting
```

Do not create scheduled prompts unless the owner asks.

## Policy Choices

```text
入定
  Stable/default. Good when the owner is away or wants low risk.
  Lower failure backlash and lighter idle loss.

冲关
  Aggressive. Good when near breakthrough and current state is clean.
  Higher successful qi gain, but failure and idle backlash are heavier.

淬心
  Defensive. Good when heart demon is high or recent failures occurred.
  Suppresses heart demon and improves recovery after rough streaks.

悟道
  Insight-focused. Good for thinking/research/planning-heavy days.
  More comprehension from review/insight, slightly lower qi.

调息
  Recovery-focused. Good when fatigue is high.
  Stronger fatigue recovery and conservative gains.
```

## Natural-Language Mapping

```text
稳一点 / 默认 / 今天不用你 / 挂着 -> 入定
冲 / 冲关 / 今天冲一把 / 加速 -> 冲关
压心魔 / 心魔高 / 稳心 / 保道心 -> 淬心
研究 / 推演 / 悟性 / 多想想 -> 悟道
休息 / 累了 / 降疲劳 / 恢复状态 -> 调息
```

If ambiguous, ask once. Do not guess from vague mood text.

## Recommendation Rules

```text
heart demon high or recent failures -> 淬心
fatigue high -> 调息
low heart demon + low fatigue + near breakthrough -> 冲关
planning/research-heavy conversation -> 悟道
owner leaving / unclear usage today -> 入定
```

Keep replies short:

```text
已切冲关：成功灵气更高，失败反噬也更重。
已切淬心：先压心魔，稳住道心。
已切调息：今天优先恢复疲劳。
```

## Idle-Time Preference

Use the owner-approved 1-2-3-4-5 day rhythm. Idle is not meant to punish light absence; only sustained neglect plus bad state risks regression.
