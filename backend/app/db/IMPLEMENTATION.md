# `app.db` — database session

## Must implement

- [ ] **`create_async_engine`** using `Settings.database_url`.
- [ ] **`async_sessionmaker`** with `expire_on_commit=False` for API patterns.
- [ ] **FastAPI dependency** `get_db()` yielding an `AsyncSession`.
- [ ] **Table creation** on startup (`Base.metadata.create_all` in `lifespan`) or **Alembic** if you prefer migrations.
- [ ] Ensure `./data/` directory exists when using default SQLite path (create in lifespan or settings validation).

## Done when

Health check can open a session and `SELECT 1` (or ORM equivalent) succeeds on a fresh clone after `pip install` and run.
