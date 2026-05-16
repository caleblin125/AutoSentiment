# `app.core` — configuration

## Must implement

- [ ] **Secrets**: Ensure `.env` is gitignored; document all required env vars in `backend/.env.example`.
- [ ] **Database URL**: Support `sqlite+aiosqlite` for dev; keep URL parsing compatible with SQLAlchemy 2 `create_async_engine`.
- [ ] **CORS**: `CORS_ORIGINS` as comma-separated list; default must match Vite dev server ports.
- [ ] **Optional**: Add `log_level`, `max_agent_steps`, `agent_timeout_seconds` for hackathon tuning without code changes.

## Done when

Changing origins or DB path does not require editing Python constants — only `.env`.
