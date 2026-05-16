# `app.reports` — grounded synthesis

## Model split

- **Primary requirement**: synthesis must **only** cite evidence IDs present in the input list (validate after generation).
- **Nemoclaw** is appropriate for **final** narrative structure, section planning, or resolving contradictions — expensive but higher quality.
- **Lightweight** models are generally **not** suitable for long-form synthesis unless strongly constrained; prefer Nemoclaw here when budget allows.

## Must implement

- [ ] **Input**: structured list of evidence objects (id, url, excerpt).
- [ ] **Output JSON schema** (suggested):
  - `sections[]`: `{ title, paragraphs: [{ text, citation_ids: string[] }] }`
  - `unknowns[]`: gaps where evidence was insufficient.
- [ ] **LLM prompt constraints**: model must not cite IDs not in the input list; post-validate and strip/repair offending paragraphs.
- [ ] **Optional**: Nemoclaw pass for polish **after** draft sections exist, still re-validating citations.
- [ ] **Export**: optional Markdown serializer that footnotes evidence IDs.

## Done when

Automated check: every `citation_ids` entry resolves to an existing `EvidenceChunk.id` for that run.
