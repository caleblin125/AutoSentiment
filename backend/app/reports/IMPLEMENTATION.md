# `app.reports` — grounded synthesis

## Must implement

- [ ] **Input**: structured list of evidence objects (id, url, excerpt).
- [ ] **Output JSON schema** (suggested):
  - `sections[]`: `{ title, paragraphs: [{ text, citation_ids: string[] }] }`
  - `unknowns[]`: gaps where evidence was insufficient.
- [ ] **LLM prompt constraints**: model must not cite IDs not in the input list; post-validate and strip/repair offending paragraphs.
- [ ] **Export**: optional Markdown serializer that footnotes evidence IDs.

## Done when

Automated check: every `citation_ids` entry resolves to an existing `EvidenceChunk.id` for that run.
