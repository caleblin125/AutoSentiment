# `app.retrieve` — evidence retrieval

## Must implement

- [ ] **Query chunks scoped to `run_id`** (never leak other runs).
- [ ] **FTS5** over `EvidenceChunk.text` **or** acceptable fallback: `LIKE` / Python scoring for demo only (document limitations).
- [ ] **Top-k** + optional **MMR**-style diversity (stretch).
- [ ] Return structure usable by report builder: list of `{ "evidence_id", "snippet", "source_url", "score" }`.

## Done when

For each sub-question, retrieval returns a bounded set of chunks that human readers find relevant in spot checks.
