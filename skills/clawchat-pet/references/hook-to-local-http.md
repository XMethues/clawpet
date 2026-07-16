# Event Delivery Notes

Use this reference when explaining how Hermes activity affects 银月 at a gameplay level.

Hermes activity is turned into cultivation events immediately. Those events update qi, heart demon, fatigue, dao heart, comprehension, fate, realm progress, voice, and recent logs.

If the local game service is briefly unavailable, the event is skipped instead of replayed later. This keeps the game state understandable: 银月 should not suddenly gain or lose progress from old delayed events.

Player-facing summary:

```text
activity now -> game change now
missed moment -> skipped, not replayed later
```
