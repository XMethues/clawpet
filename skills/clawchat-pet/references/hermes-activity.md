# Hermes Activity Notes

Use this reference when explaining how Hermes activity affects the current pet at a gameplay level.

Hermes hooks call the authoritative runtime directly in the plugin process. The runtime interprets each lifecycle event, atomically commits any one-time shared-growth effect, and updates the transient aggregate activity display only after that commit succeeds. There is no HTTP event-delivery path and no replay queue.

The selected gameplay scene names and narrates settled facts only when `/presentation` is read. Approval rejection, timeout, interruption, subagent lifecycle, and unknown tool results remain neutral.

```text
Hermes callback -> in-process interpretation -> atomic save -> presentation
failed commit   -> event skipped, not replayed later
```
