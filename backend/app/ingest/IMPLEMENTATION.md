# `app.ingest` — fetch & normalize

## Must implement

- [ ] **`httpx.AsyncClient`** with timeouts, user-agent, redirect limits; optional per-host rate limit for hackathon safety.
- [ ] **HTML → text** using `trafilatura` (or fallback: readability-lxml / plain BS4).
- [ ] **Chunking**: sentence- or token-aware splits; store stable `chunk_index` per URL.
- [ ] **Dedupe**: hash `(run_id, url, chunk_index)` or content hash to skip duplicates.
- [ ] **Robots / ToS**: document in README that operators must comply; optional robots check is a stretch goal.

## Done when

Given a list of URLs, the run stores multiple `EvidenceChunk` rows with non-empty `text` for most static pages.
