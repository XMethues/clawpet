# Event Delivery Notes

Use this reference when explaining how Hermes activity affects the current pet at a gameplay level.

Hermes activity is turned into growth events immediately. Those events update the shared progress meters, stage position, semantic facts, voice cue, and recent history. The selected gameplay scene names and narrates those settled facts only when the experience view is read.

If the local game service is briefly unavailable, the event is skipped instead of replayed later. This keeps the game state understandable: the pet should not suddenly gain or lose progress from old delayed events.

Player-facing summary:

```text
activity now -> game change now
missed moment -> skipped, not replayed later
```
