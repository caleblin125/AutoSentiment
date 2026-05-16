# `app.models` — persistence models

## Must implement (suggested tables)

- [ ] **`Run`**: `id`, `status` (pending/running/completed/failed), `query` or `prompt`, `created_at`, `updated_at`, optional `report_json` / `report_md`.
- [ ] **`RunEvent`**: `id`, `run_id`, `seq` monotonic per run, `event_type`, `payload_json`, `created_at` — append-only log for SSE replay (optional but useful).
- [ ] **`EvidenceChunk`**: `id`, `run_id`, `source_url`, `retrieved_at`, `text`, `chunk_index`, optional `title`, `hash` for dedupe.
- [ ] **`RawArtifact`** (optional v0): `id`, `run_id`, `url`, `content_type`, `body` blob or filesystem path.

## FTS5 (optional but recommended)

- [ ] Either: virtual table synced from `EvidenceChunk.text`, or generated columns + FTS index — see `retrieve/IMPLEMENTATION.md`.

## Done when

You can list all chunks for a `run_id` and join them to the final report citation IDs.
