# AutoSentiment — NemoClaw Self-Analysis

**Model**: nemotron-3-super
**Date**: 2026-05-16T15:39:51.336431

## Verdict

Project shows solid engineering with thoughtful design for LLM pipelines, SSE streaming, and modular components, but suffers from SQLite scalability limits, untested real-world usage under rate limits, and missing production-grade observability and security.

## Strengths

- Well-structured async pipeline with clear separation of concerns (search, fetch, sentiment, synthesis)
- Effective SSE event streaming with replay and detailed timing metrics
- Strong use of local LLMs via Ollama with fallback considerations and model isolation
- Evidence traceability: every snippet links to source URL and includes confidence/justification
- Good test coverage for core components and adherence to Brave rate limits

## Problems

- **[HIGH] [architecture]** SQLite backend limits concurrent writes and horizontal scaling; WAL mode helps but cannot support multiple backend instances or high write throughput from parallel sentiment/fetch tasks.
  - Impact: Will fail under modest production load; cannot run multiple workers or scale beyond single-node deployment.
- **[HIGH] [reliability]** Orchestrator test hangs due to SQLite session contamination; indicates test isolation issues that could mask race conditions or connection leaks in production.
  - Impact: Undetected bugs in async session handling may cause data corruption or deadlocks under load.
- **[MEDIUM] [performance]** No client-side caching or request deduplication in frontend; repeated runs re-fetch and re-analyze identical URLs despite URL cache in backend.
  - Impact: Wastes compute, increases latency, and unnecessarily consumes Brave quota and LLM tokens.
- **[MEDIUM] [security]** Brave API key stored only in .env with no encryption at rest; no API key rotation or restricted scoped keys supported.
  - Impact: If container or host is compromised, API key is exposed and could be abused beyond quota.
- **[LOW] [ux]** Evidence modal shows keyword highlighting but lacks snippet context toggling or sentiment confidence visualization (e.g., bar or color intensity).
  - Impact: Users must trust model output without insight into uncertainty, reducing analytical rigor.

## Suggestions

- **[HIGH] [architecture]** (large effort) Replace SQLite with PostgreSQL (or MySQL) to support concurrent writes, connection pooling, and horizontal scaling. Keep Alembic migrations for schema updates.
- **[HIGH] [testing]** (medium effort) Fix test isolation by using function-scoped in-memory SQLite databases with engine disposal; add pytest fixtures that drop_all/create_all per test.
- **[MEDIUM] [performance]** (medium effort) Add frontend memoization of search results and evidence chunks by topic/freshness/depth hash; show 'using cached data' badge to avoid redundant work.
- **[MEDIUM] [security]** (medium effort) Encrypt .env at rest using a derived key (e.g., from a passphrase) or integrate with Docker secrets / HashiCorp Vault for API key management.
- **[LOW] [ux]** (small effort) Add sentiment confidence visualization in evidence modal (e.g., tooltip showing probability distribution from model logits or a confidence bar).

## Missing Features

- User authentication and role-based access control (admin vs analyst vs viewer)
- Export reports in PDF/JSON/CSV with citations and evidence appendix
- Webhook or email alerts when sentiment crosses thresholds for a topic
- Multi-tenancy support for team or organizational use
- Dark mode toggle and accessibility (WCAG AA) audit

## Risks

- SQLite corruption under concurrent writes during high parallelism (fetch + sentiment + event logging)
- Brave quota exhaustion due to unbounded expansion depth or retry loops
- Ollama model unavailability causing cascading failures without graceful degradation
- Frontend memory leak from accumulating event streams without cleanup
- LLM prompt injection via topic field despite current guard (needs ongoing validation)

## Architecture Notes

The pipeline architecture is a strength: clear stage separation, async event bus, and modular agents (NemoClaw, light_queue) make it maintainable. Use of SQLAlchemy async and FastAPI is appropriate. However, over-reliance on SQLite as a single point of failure undermines the otherwise robust design. The SSE implementation is solid, but event_bus lacks backpressure handling. The separation of synthesis (120B) and sentiment (30B) is smart for resource scheduling. Overall, the code reflects senior-level engineering but lacks production hardening.