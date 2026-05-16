#!/usr/bin/env python3
"""Compare Ollama vs direct llama.cpp server inference speed.

This benchmark sends identical prompts to both backends and measures
time-to-first-token (TTFT), total generation time, and tokens/second.

Usage:
    cd backend && source .venv/bin/activate
    python3 scripts/benchmark_llamacpp.py [--model MODEL_NAME] [--runs 3]

Prerequisites:
    - Ollama running on default port (11434)
    - llama.cpp server running (e.g., via ~/llama.cpp/llama-server)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass
from typing import Optional

import httpx

OLLAMA_BASE = "http://localhost:11434"
LLAMACPP_BASE = "http://localhost:8080"

TEST_PROMPTS = [
    # Short sentiment prompt (30B style)
    (
        "sentiment-short",
        "You are a sentiment classifier. Classify this text as positive, neutral, or negative only.\n\n"
        'Text: "The product exceeded expectations in every way. I would absolutely recommend it to anyone."\nSentiment:',
        30,
    ),
    # Medium synthesis prompt (120B style)  
    (
        "synthesis-medium",
        "You are a research analyst. Given the following sentiment counts for 'Electric Vehicles' "
        "(positive: 45%, neutral: 25%, negative: 30%) and key themes: battery range, charging infrastructure, "
        "cost, environmental impact — write a 2-paragraph narrative summarizing public opinion.",
        200,
    ),
    # Long expansion prompt (120B style)
    (
        "expansion-long",
        "Expand the search query 'AI regulation policy' into 5 diverse search queries that cover: "
        "official government sources, public opinion, expert analysis, international comparisons, "
        "and industry impact. Write one query per line. Be specific.",
        120,
    ),
]


@dataclass
class BenchResult:
    label: str
    backend: str
    ttft_ms: float
    total_ms: float
    token_count: int
    tokens_per_sec: float


async def bench_ollama(
    client: httpx.AsyncClient,
    model: str,
    prompt: str,
    max_tokens: int,
    label: str,
) -> BenchResult:
    """Stream completion from Ollama, measuring TTFT and total time."""
    t0 = time.perf_counter()
    ttft: Optional[float] = None
    token_texts: list[str] = []

    url = f"{OLLAMA_BASE}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {"num_predict": max_tokens, "temperature": 0.0},
    }

    async with client.stream("POST", url, json=payload, timeout=120) as resp:
        async for line in resp.aiter_lines():
            if not line.strip():
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ttft is None and chunk.get("response"):
                ttft = time.perf_counter() - t0
            if chunk.get("response"):
                token_texts.append(chunk["response"])
            if chunk.get("done"):
                break

    total_ms = (time.perf_counter() - t0) * 1000
    ttft_ms = (ttft or total_ms / 1000) * 1000
    token_count = len(token_texts) or 1

    return BenchResult(
        label=label,
        backend="ollama",
        ttft_ms=round(ttft_ms, 1),
        total_ms=round(total_ms, 1),
        token_count=token_count,
        tokens_per_sec=round(token_count / max(total_ms / 1000, 0.001), 1),
    )


async def bench_llamacpp(
    client: httpx.AsyncClient,
    model: str,
    prompt: str,
    max_tokens: int,
    label: str,
) -> BenchResult:
    """Stream completion from llama.cpp server, measuring TTFT and total time."""
    t0 = time.perf_counter()
    ttft: Optional[float] = None
    token_count = 0

    url = f"{LLAMACPP_BASE}/completion"
    payload = {
        "prompt": prompt,
        "n_predict": max_tokens,
        "temperature": 0.0,
        "stream": True,
        "cache_prompt": True,
    }

    try:
        async with client.stream("POST", url, json=payload, timeout=120) as resp:
            async for line in resp.aiter_lines():
                if not line.strip() or not line.startswith("data: "):
                    continue
                data_str = line[len("data: "):]
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                if ttft is None and chunk.get("content"):
                    ttft = time.perf_counter() - t0
                if chunk.get("content"):
                    token_count += 1
                if chunk.get("stop"):
                    break
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        return BenchResult(
            label=label, backend="llamacpp",
            ttft_ms=0, total_ms=0, token_count=0, tokens_per_sec=0,
        )
        # Store error info in a way that prints clearly.
        setattr(
            locals().get("result", None) or (),
            "_error",
            str(exc),
        )

    total_ms = (time.perf_counter() - t0) * 1000
    ttft_ms = (ttft or total_ms / 1000) * 1000
    token_count = max(token_count, 1)

    return BenchResult(
        label=label,
        backend="llamacpp",
        ttft_ms=round(ttft_ms, 1),
        total_ms=round(total_ms, 1),
        token_count=token_count,
        tokens_per_sec=round(token_count / max(total_ms / 1000, 0.001), 1),
    )


async def check_health(client: httpx.AsyncClient, url: str, name: str) -> bool:
    try:
        resp = await client.get(url, timeout=5)
        return resp.status_code < 500
    except Exception:
        return False


async def main():
    parser = argparse.ArgumentParser(description="llama.cpp vs Ollama benchmark")
    parser.add_argument("--model", default="nemotron-3-nano", help="Model name for both backends")
    parser.add_argument("--runs", type=int, default=3, help="Number of runs per prompt")
    parser.add_argument("--ollama-only", action="store_true", help="Skip llama.cpp (if not running)")
    parser.add_argument("--llamacpp-only", action="store_true", help="Skip Ollama (if not running)")
    args = parser.parse_args()

    async with httpx.AsyncClient() as client:
        # Health checks
        ollama_ok = await check_health(client, f"{OLLAMA_BASE}/api/tags", "Ollama")
        llamacpp_ok = await check_health(client, f"{LLAMACPP_BASE}/health", "llama.cpp")

        print("=" * 72)
        print("AutoSentiment — llama.cpp vs Ollama Inference Benchmark")
        print(f"Model: {args.model}  |  Runs per prompt: {args.runs}")
        print(f"Ollama: {'✓ running' if ollama_ok else '✗ unavailable'}  |  "
              f"llama.cpp: {'✓ running' if llamacpp_ok else '✗ unavailable'}")
        print("=" * 72)

        if not ollama_ok and not llamacpp_ok:
            print("\nERROR: Neither backend is reachable. Start at least one server.")
            return

        results: list[BenchResult] = []

        for run_idx in range(args.runs):
            if args.runs > 1:
                print(f"\n── Run {run_idx + 1}/{args.runs} ──")

            for label, prompt, max_tokens in TEST_PROMPTS:
                tasks = []
                if ollama_ok and not args.llamacpp_only:
                    tasks.append(bench_ollama(client, args.model, prompt, max_tokens, label))
                if llamacpp_ok and not args.ollama_only:
                    tasks.append(bench_llamacpp(client, args.model, prompt, max_tokens, label))

                batch = await asyncio.gather(*tasks)
                results.extend(batch)

                for r in batch:
                    status = "✓" if r.token_count > 1 else "✗"
                    print(f"  {status} [{r.backend:>9s}] {r.label:<18s}  "
                          f"TTFT: {r.ttft_ms:>7.1f}ms  "
                          f"Total: {r.total_ms:>8.1f}ms  "
                          f"Tokens: {r.token_count:>4d}  "
                          f"Speed: {r.tokens_per_sec:>7.1f} tok/s")

        # ── Summary ──
        print("\n" + "=" * 72)
        print("Summary (averages)")
        print("=" * 72)

        backends = sorted({r.backend for r in results})
        for backend in backends:
            backend_results = [r for r in results if r.backend == backend]
            if not backend_results:
                continue
            avg_ttft = sum(r.ttft_ms for r in backend_results) / len(backend_results)
            avg_total = sum(r.total_ms for r in backend_results) / len(backend_results)
            avg_tps = sum(r.tokens_per_sec for r in backend_results) / len(backend_results)
            print(f"  {backend:>9s}:  avg TTFT {avg_ttft:>7.1f}ms  "
                  f"avg total {avg_total:>8.1f}ms  "
                  f"avg {avg_tps:>7.1f} tok/s")

        if len(backends) >= 2:
            ollama_results = [r for r in results if r.backend == "ollama"]
            llamacpp_results = [r for r in results if r.backend == "llamacpp"]
            if ollama_results and llamacpp_results:
                ollama_tps = sum(r.tokens_per_sec for r in ollama_results) / len(ollama_results)
                llamacpp_tps = sum(r.tokens_per_sec for r in llamacpp_results) / len(llamacpp_results)
                ratio = llamacpp_tps / max(ollama_tps, 0.01)
                faster = "llama.cpp" if ratio > 1.05 else "Ollama"
                print(f"\n  Speed ratio: llama.cpp / Ollama = {ratio:.2f}x"
                      f"  → {faster} is faster")
                if ratio > 1.1:
                    print("  Recommendation: Use llama.cpp server for production inference.")
                elif ratio < 0.9:
                    print("  Recommendation: Ollama is sufficient; no compelling reason to switch.")
                else:
                    print("  Recommendation: Performance is comparable. Choose based on operational needs.")


if __name__ == "__main__":
    asyncio.run(main())
