# `app.memory` — run state & checkpoints

## Must implement (minimum)

- [ ] **Run status transitions** in DB: pending → running → completed | failed.
- [ ] **Optional** `RunEvent` append log for debugging and SSE replay.

## Stretch (post-MVP)

- [ ] User/project memory across runs.
- [ ] Watchlists & scheduled re-runs.

## Done when

Every completed run has a terminal status and timestamp; failures are observable in API/SSE.
