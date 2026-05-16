# Hackathon environment (NemoClaw / Hack-a-Claw)

This project targets the **Hack-a-Claw** hackathon and the **NVIDIA NemoClaw** stack. Spelling varies by surface (`nemoclaw` in URLs, `NemoClaw` in NVIDIA docs).

## Official references

| Resource | Notes |
|----------|--------|
| [shortesthack.com — Nemoclaw tab](https://www.shortesthack.com/?tab=nemoclaw) | Event site; **tab content is loaded in the browser** — use the live page plus organizer chat for exact model names, API bases, and secrets. |
| [NVIDIA NemoClaw Developer Guide](https://docs.nvidia.com/nemoclaw/latest/index.html) | What NemoClaw is: OpenClaw assistants in **OpenShell** sandboxes, onboarding, inference routing, network policies. Install entrypoint: `curl -fsSL https://www.nvidia.com/nemoclaw.sh \| bash`. |
| [NemoClaw NVIDIA × ASUS Hackathon @ UCSC](https://events.ucsc.edu/event/nvidia-hackathon-2026/) | **Edge track:** on-site **ASUS DGX Spark**. **Cloud track:** sponsored instances via [Brev.dev](https://brev.dev/). Unified stack for both tracks. |

## How this maps to `AutoSentiment`

| Concept in this repo | In the hackathon environment |
|----------------------|------------------------------|
| **Nemoclaw tier** (`NEMCLAW_MODEL`, `app/agents/nemoclaw.py`) | Use the **orchestrator / planning** model **your NemoClaw onboarding or hackathon inference routing exposes** (high-capability route). This matches NemoClaw’s role: structure agent work safely inside the sandbox. |
| **Lightweight tier** (`LIGHTWEIGHT_MODEL`, `LIGHT_QUEUE_MAX_PARALLEL`) | Use a **faster, cheaper** model or endpoint the environment provides for search-adjacent LLM calls (query expansion, snippet scoring, quick filters). Queue width caps parallelism so you do not overwhelm shared inference. |
| **Secrets** | Prefer **env vars and NemoClaw/OpenShell patterns** from the hackathon brief — do not commit `.env`. |

## Practical checklist before you hack

1. Open [shortesthack.com/?tab=nemoclaw](https://www.shortesthack.com/?tab=nemoclaw) in a browser and copy any **model IDs, base URLs, or setup steps** into your team runbook.  
2. Complete **NemoClaw quickstart** (or cloud/edge-specific steps) so a sandboxed agent can call inference.  
3. Set `NEMCLAW_MODEL` and `LIGHTWEIGHT_MODEL` in `backend/.env` to match **exact** identifiers from your environment (they may differ from defaults in `app/core/config.py`).  
4. Confirm **egress/network policy** in NemoClaw allows HTTP(S) to your search provider and target sites (see NVIDIA docs on network policies).

## Disclaimer

Hackathon specifics (exact model strings, quotas, approved tools) **change** — treat the live organizer materials and NemoClaw docs as authoritative over this scaffold.
