# Agent Task Queue — Remaining

Last audit: 2026-05-16 22:10 UTC

## ✅ JUST DONE (NemoClaw Round 2 findings)
- [x] Wire batch sentiment into orchestrator (analyze_batch now used for uncached snippets)
- [x] URL fetch retry with exponential backoff (3 attempts, 15s timeout each)
- [x] Quota bar indicator in budget preview (visual bar + remaining count)

## ✅ PREVIOUSLY DONE
- [x] Retry + circuit breaker on Ollama calls
- [x] Prompt injection guard on topic input
- [x] Evidence modal: keyword highlighting + justification + confidence
- [x] SQLite WAL mode + pragmas
- [x] Per-item sentiment failure recovery
- [x] All 12 objectives, UI overhaul, search optimization, reliability hardening, UX polish

## 🔴 REMAINING — 5 items

### 1. Fix orchestrator test hangs
8 tests hang together from SQLite session contamination. All pass individually.
Fix: isolated in-memory DB per test function with proper teardown.

### 2. LLM failure injection tests
New test file: mock Ollama returning 500s, timeouts, malformed JSON.
Verify retry logic fires and circuit breaker opens/closes correctly.

### 3. Extract synthesis interface
Decouple LLM prompt templates from builder.py and nemoclaw.py.
Create LLMService protocol that both modules depend on.

### 4. Admin dashboard (frontend)
Page showing: quota usage over time, model availability, run success/error rates.
Expose via /api/admin/stats endpoint.

### 5. Model fallback
Auto-try smaller model if 30B/120B unavailable (ollama_generate with fallback_model param).
