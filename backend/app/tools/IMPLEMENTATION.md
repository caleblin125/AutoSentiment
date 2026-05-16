# `app.tools` — external capabilities

## Must implement

- [ ] **`search_web(query, *, max_results) -> list[dict]`** returning at least `{ "url", "title", "snippet" }` per result.
- [ ] **Provider abstraction**: one module per vendor (e.g. Brave, SerpAPI, etc.); select via env `SEARCH_PROVIDER`.
- [ ] **Secrets**: read API keys from settings / env only; never log full keys.
- [ ] **Rate limits**: simple sleep or token bucket if you hit quotas during demo.

## Done when

Orchestrator can obtain a diverse set of URLs for a research query without manual copy-paste.
