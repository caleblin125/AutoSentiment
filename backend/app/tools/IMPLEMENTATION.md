# `app.tools` — external capabilities

## Model split

- **Nemoclaw** does *not* live here — planning is `app.agents.nemoclaw`.
- **Lightweight models** *do* support tool-heavy flows: before/after calling `search_web`, use `LightweightModelQueue` for reformulation, intent labels, or snippet scoring (keep prompts short).

## Must implement

- [ ] **`search_web(query, *, max_results) -> list[dict]`** returning at least `{ "url", "title", "snippet" }` per result.
- [ ] **Optional integration**: for each seed query from `ResearchPlan.search_program`, call light tier to produce **additional** queries before hitting the search API.
- [ ] **Provider abstraction**: one module per vendor (e.g. Brave, SerpAPI, etc.); select via env `SEARCH_PROVIDER`.
- [ ] **Secrets**: read API keys from settings / env only; never log full keys.
- [ ] **Rate limits**: simple sleep or token bucket if you hit quotas during demo.

## Done when

Orchestrator obtains a diverse set of URLs using Nemoclaw’s structure plus lightweight query helpers where useful.
