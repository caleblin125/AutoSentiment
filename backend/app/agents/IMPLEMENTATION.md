# `app.agents` — orchestration

## Must implement

- [ ] **`run_research(run_id)`** (or equivalent) loaded with settings: **max steps**, **per-step timeout**, **max URLs fetched**.
- [ ] **Phases** (flexible order, but must be traceable):
  1. Plan: break query into sub-questions (LLM or heuristic).
  2. Discover: search tool returns candidate URLs.
  3. Ingest: fetch + extract + chunk + persist `EvidenceChunk` rows.
  4. Retrieve: pull top chunks for each sub-question (FTS / keyword).
  5. Synthesize: call `reports` builder with **only** retrieved chunk IDs.
- [ ] **Emit events** after each meaningful transition (for SSE). Persist to `RunEvent` if you want replay.
- [ ] **Failure handling**: capture stack or message into run status + final error event.

## Done when

A run produces stored evidence rows and a report that references only existing `EvidenceChunk.id` values.
