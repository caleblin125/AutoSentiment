# `app.agents` — orchestration

## Architecture: Nemoclaw + lightweight queue

1. **Nemoclaw** (`nemoclaw.py`, model `NEMCLAW_MODEL`)  
   - **Organizes** the run: `ResearchPlan` with `sub_questions`, `search_program`, `processing_order`, `notes_for_light_tier`.  
   - Does **not** replace search APIs or bulk fetch — it decides *what* to pursue and *in what order*.

2. **Lightweight model queue** (`light_queue.py`, model `LIGHTWEIGHT_MODEL`)  
   - **Queued** in-process with **bounded parallelism** (`LIGHT_QUEUE_MAX_PARALLEL`).  
   - Use for **cheap** LLM work: query expansion, SERP/snippet scoring, quick chunk filters (`LightJobKind` in `types.py`).  
   - Avoid heavy reasoning here; route synthesis or conflict resolution to Nemoclaw when needed.

3. **Orchestrator** (`orchestrator.py`)  
   - Wires: plan → light jobs → `tools` / `ingest` / `retrieve` / `reports`.

## Must implement

- [ ] **`structure_research_plan`** — real Nemoclaw LLM call, JSON parse/validate into `ResearchPlan`.
- [ ] **`LightweightModelQueue._invoke`** — provider SDK/HTTP for each `LightJobKind`; unit budgets (max tokens, timeout).
- [ ] **`run_research(run_id, user_query, settings)`** — full pipeline with **max steps**, **timeouts**, **max URLs**; persist state.
- [ ] **Phases** (traceable; align with `ResearchPlan.processing_order`):
  1. **Plan** — Nemoclaw produces `ResearchPlan`.
  2. **Discover** — expand seeds via light queue; search tool returns candidate URLs.
  3. **Ingest** — fetch + extract + chunk + `EvidenceChunk` rows.
  4. **Retrieve** — FTS/keyword; optional light tier for rerank/filter.
  5. **Synthesize** — `reports` with evidence IDs; Nemoclaw (optional) for final narrative quality.
- [ ] **Emit events** after each transition (SSE / `RunEvent`).
- [ ] **Failure handling** — run status + error event on stack/validation errors.

## Done when

A run shows **Nemoclaw** plan metadata in logs or events, **light** jobs respect concurrency cap, stored evidence exists, and the report cites only real chunk IDs.
