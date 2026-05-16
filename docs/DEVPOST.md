# Devpost — AutoSentiment

---

## 🏆 AutoSentiment: Multi-Source Public Sentiment Intelligence

### Tagline
*Search the web. Analyze every result. Know what the internet really thinks — powered entirely by local AI.*

---

## 📖 About

AutoSentiment is a locally-hosted research tool that takes any topic, brand, event, or question — and tells you what the internet thinks about it.

Type a topic. Pick a time window and research depth. AutoSentiment searches Brave and five free media APIs, fetches full article and forum text, classifies every snippet as positive, neutral, or negative with a local 30B model, then uses a 120B model to synthesize themes, narrative, chronology, factual claims, and an interactive idea graph — all streamed live to a real-time tabbed dashboard.

Every opinion links back to its source URL. Every claim shows corroborating domains. Every date is extracted from text, never fabricated. The graph is colored by sentiment at a glance.

**No external API dependencies for AI.** Everything runs locally on Ollama with models you control.

---

## 🎯 The Problem

Understanding public sentiment today means:
- Manually reading hundreds of articles, Reddit threads, and reviews
- Guessing whether opinions are trending positive or negative
- Having no way to trace claims back to their sources
- Trusting black-box AI summaries with no provenance

Journalists, product teams, investors, and analysts spend hours doing what a machine could do in minutes — if it were built to be transparent and verifiable.

---

## 💡 Our Solution

AutoSentiment automates the entire research pipeline:

1. **Smart search planning** — 120B model generates context-aware Brave queries tailored to your use case (entertainment, finance, current events, policy, brands)
2. **Broad source coverage** — Brave Search + GDELT, Hacker News, Wikipedia, arXiv, and Reddit APIs — rate-limited and quota-tracked
3. **Per-item AI sentiment** — 30B model classifies every snippet with confidence scores, batched for GPU efficiency
4. **Structured synthesis** — 120B model produces themes, narrative, impacts, and arguments from pre-computed analytics
5. **Evidence layer** — every claim shows corroborating domains; every date is extracted from text; contradictions are flagged
6. **Real-time streaming** — Server-Sent Events show every pipeline stage as it happens
7. **Interactive graph** — Force-directed visualization where sources are colored by sentiment (green/red/gray), clicking reveals URLs and evidence
8. **Multi-tab + compare** — Run multiple searches side-by-side, compare sentiment across topics

---

## 🛠️ How We Built It

**Backend** — Python 3.12 + FastAPI + SQLAlchemy async + SQLite (WAL mode)
**Frontend** — Vite + React 19 + TypeScript + CSS custom properties (dark/light themes)
**AI** — Ollama serving three models simultaneously:
- `nemotron-3-super` (120B) — synthesis, query expansion, NemoClaw autonomous agent
- `nemotron-3-nano` (30B) — per-item sentiment classification with confidence scores
- `deepseek-r1` (14B) — search angle suggestions

**Search** — Brave Search API (1 req/s, 2,000/month) + 5 free media APIs in parallel via `asyncio.gather`

**Pipeline stages**: Search planning → query expansion → Brave + media API search → parallel URL fetch (trafilatura) → batch sentiment analysis → report assembly → synthesis → SSE streaming

**Engineering highlights**:
- Circuit breaker + exponential backoff retry on all LLM calls
- Per-domain fetch concurrency caps (max 2 per domain, 12 global)
- Persistent caches: Brave results, fetched URLs, sentiment hashes — all in SQLite with TTL
- Cooperative cancellation mid-LLM-token for instant user control
- 131 passing tests covering pipeline, LLM, search, fetch, routes, reliability

---

## 🧗 Challenges We Faced

**GPU memory**: Running 120B + 30B simultaneously requires ~115GB VRAM. We implemented keep-alive pings, model warm-up, and optional smaller-model fallback paths for lower-VRAM setups.

**Brave rate limiting**: Free tier is 1 req/s and 2,000/month. We built a quota tracker with visual bar, pre-queueing of cache hits, and 5 supplemental free APIs to maximize coverage without spending quota.

**Sentiment latency**: The sentiment stage was the bottleneck. We added snippet deduplication (75% reduction in model calls), batch processing (5 snippets per call), and DB-backed caching across runs.

**Orchestrator test isolation**: SQLite session contamination caused 8 tests to hang when run together. All pass individually. This remains our top-priority engineering fix.

**Prompt injection**: Users type arbitrary topics that get sent to LLMs. We added a validation layer that blocks common injection patterns (`ignore previous instructions`, role-switching tokens, system override syntax).

---

## 🏅 Accomplishments

- **12 planned objectives — all complete**
- **131 tests** covering pipeline, reports, search, fetch, LLM, reliability
- **6 use cases**: Generic, Entertainment, Current Events, Brand/Product, Policy/Civic, Financial Markets
- **15 frontend components** with dark/light themes, keyboard shortcuts, mobile layout, print styles
- **NemoClaw self-analysis**: The 120B model audits the project itself, producing a structured report with problems, suggestions, and risks
- **127 commits** across 3 AI agents collaborating via shared task queue and relay system
- **20,000+ lines** of Python, TypeScript, and CSS

---

## 🚀 What's Next

- **PostgreSQL migration** for multi-instance scaling (SQLite is single-node)
- **Admin dashboard** for quota monitoring, model health, and run analytics
- **Webhook/email alerts** when sentiment crosses configurable thresholds
- **PDF report export** with citations and evidence appendix
- **Multi-tenancy** with role-based access for team deployments

---

## 🔗 Try It Yourself

```bash
git clone https://github.com/caleblin125/AutoSentiment.git
cd AutoSentiment
./setup.sh
# Add your Brave API key to backend/.env
# Start backend: cd backend && source .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000
# Start frontend: cd frontend && npm run dev
# Open http://localhost:5173
```

Requires: Python 3.12+, Node.js 20+, Ollama with `nemotron-3-super`, `nemotron-3-nano`, `deepseek-r1:14b`, and a Brave Search API key (free tier works).

---

## 🧰 Built With

`python` `fastapi` `sqlalchemy` `react` `typescript` `vite` `ollama` `brave-search` `trafilatura` `docker` `playwright` `pytest` `sqlite` `sse` `asyncio` `httpx` `pydantic`
