#!/usr/bin/env python3
"""End-to-end smoke test for the AutoSentiment pipeline.

Starts the backend, creates a quick run, waits for completion, and validates
the report shape. Exits 0 on success, 1 on failure.

Usage:
    cd backend && source .venv/bin/activate
    python3 scripts/e2e_smoke_test.py [--port 8010] [--topic "Test query"]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

BACKEND_DIR = Path(__file__).resolve().parent.parent
API_BASE = "http://127.0.0.1"


def green(s: str) -> str: return f"\033[32m{s}\033[0m"
def red(s: str) -> str: return f"\033[31m{s}\033[0m"
def bold(s: str) -> str: return f"\033[1m{s}\033[0m"


async def wait_for_health(client: httpx.AsyncClient, port: int, timeout: float = 15) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = await client.get(f"{API_BASE}:{port}/api/health", timeout=3)
            if resp.status_code == 200:
                return True
        except Exception:
            pass
        await asyncio.sleep(0.5)
    return False


async def main():
    parser = argparse.ArgumentParser(description="AutoSentiment E2E smoke test")
    parser.add_argument("--port", type=int, default=8010, help="Backend port")
    parser.add_argument("--topic", default="Python programming language", help="Test search topic")
    args = parser.parse_args()

    port = args.port
    base = f"{API_BASE}:{port}"
    failed = False

    # ── 1. Start backend ────────────────────────────────────────────────
    print(bold("\n1. Starting backend…"))
    env = os.environ.copy()
    env.setdefault("BRAVE_API_KEY", "")

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(BACKEND_DIR),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    async with httpx.AsyncClient() as client:
        try:
            if not await wait_for_health(client, port):
                print(red("   ✗ Backend did not become healthy"))
                return 1

            # ── 2. Diagnostics ──────────────────────────────────────────
            print(bold("\n2. Checking diagnostics…"))
            diag = await client.get(f"{base}/api/diagnostics")
            assert diag.status_code == 200, f"Diagnostics failed: {diag.status_code}"
            diag_data = diag.json()
            assert diag_data["status"] in ("ok", "degraded"), f"Unexpected status: {diag_data['status']}"
            assert "brave" in diag_data, "Missing brave info"
            assert "api_key_present" in diag_data["brave"], "Missing api_key_present"
            assert "secret" not in json.dumps(diag_data).lower(), "Diagnostics leaked secret!"
            print(green(f"   ✓ Diagnostics OK (Brave key: {diag_data['brave']['api_key_present']})"))

            # ── 3. Search plan preview ──────────────────────────────────
            print(bold("\n3. Checking search plan preview…"))
            plan = await client.get(
                f"{base}/api/search-plan",
                params={"topic": args.topic, "research_depth": "quick", "use_case": "generic"},
            )
            assert plan.status_code == 200, f"Search plan failed: {plan.status_code}"
            plan_data = plan.json()
            assert "topic" in plan_data, f"Missing topic in plan: {plan_data.keys()}"
            assert "estimated_brave_queries" in plan_data, "Missing estimated queries"
            assert "queries" in plan_data and len(plan_data["queries"]) > 0, "No queries in plan"
            print(green(f"   ✓ Search plan: {len(plan_data['queries'])} queries, ~{plan_data['estimated_brave_queries']} Brave queries"))

            # ── 4. Create a run ─────────────────────────────────────────
            print(bold(f"\n4. Creating run for '{args.topic}' (quick depth)…"))
            create = await client.post(
                f"{base}/api/runs",
                json={"topic": args.topic, "research_depth": "quick", "use_case": "generic"},
            )
            assert create.status_code == 200, f"Create run failed: {create.status_code} {create.text}"
            run_data = create.json()
            run_id = run_data["run_id"]
            assert run_id, "No run_id in response"
            print(green(f"   ✓ Run created: {run_id[:8]}… (cached: {run_data.get('cached', False)})"))

            # ── 5. Wait for completion via SSE ──────────────────────────
            print(bold("\n5. Waiting for completion…"))
            completed = False
            timeout = 120  # seconds
            deadline = time.monotonic() + timeout
            last_event = None

            async with client.stream("GET", f"{base}/api/runs/{run_id}/events", timeout=timeout) as resp:
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        event = json.loads(line[len("data:"):].strip())
                    except json.JSONDecodeError:
                        continue
                    last_event = event
                    etype = event.get("type", "")
                    detail = event.get("detail", {})
                    if etype == "run_completed":
                        completed = True
                        print(green(f"   ✓ Run completed: {event.get('message', '')}"))
                        break
                    elif etype == "run_error":
                        print(red(f"   ✗ Run error: {event.get('message', '')} {detail.get('error_code', '')}"))
                        failed = True
                        break
                    elif etype == "run_cancelled":
                        print(red("   ✗ Run was cancelled"))
                        failed = True
                        break
                    if time.monotonic() > deadline:
                        print(red(f"   ✗ Timed out after {timeout}s. Last event: {last_event}"))
                        failed = True
                        break

            if not completed and not failed:
                print(red(f"   ✗ Run did not complete. Last event: {last_event}"))
                failed = True

            if failed:
                return 1

            # ── 6. Check run via GET ────────────────────────────────────
            print(bold("\n6. Checking run via GET…"))
            run_get = await client.get(f"{base}/api/runs/{run_id}")
            assert run_get.status_code == 200, f"GET run failed: {run_get.status_code}"
            run_obj = run_get.json()
            assert run_obj["status"] == "completed", f"Run not completed: {run_obj['status']}"
            assert run_obj["report"] is not None, "No report in run"
            report = run_obj["report"]
            print(green(f"   ✓ Run status: {run_obj['status']}, report present"))

            # ── 7. Validate report structure ────────────────────────────
            print(bold("\n7. Validating report structure…"))
            required = ["overall", "by_source", "top_positive", "top_negative", "themes", "narrative"]
            for key in required:
                assert key in report, f"Missing report key: {key}"
            assert isinstance(report["overall"]["total"], int), "overall.total must be int"
            assert isinstance(report["themes"], list), "themes must be list"
            assert isinstance(report["narrative"], str), "narrative must be str"
            print(green(f"   ✓ All required report keys present"))

            # Check optional sections that should be present.
            optional_checks = [
                ("aspects", list),
                ("source_facts", list),
                ("timeline", dict),
                ("fact_check", dict),
                ("threads", list),
                ("graph", dict),
                ("timings", dict),
            ]
            for key, expected_type in optional_checks:
                val = report.get(key)
                if val is not None:
                    assert isinstance(val, expected_type), f"{key} must be {expected_type.__name__}, got {type(val).__name__}"
            print(green("   ✓ All optional sections present and typed"))

            # ── 8. Check evidence endpoint ──────────────────────────────
            if report.get("top_positive"):
                evidence_id = report["top_positive"][0]["evidence_id"]
                print(bold(f"\n8. Checking evidence endpoint…"))
                ev = await client.get(f"{base}/api/runs/{run_id}/evidence/{evidence_id}")
                assert ev.status_code == 200, f"Evidence failed: {ev.status_code}"
                ev_data = ev.json()
                assert "snippet" in ev_data, "Missing snippet in evidence"
                assert "label" in ev_data, "Missing label in evidence"
                assert "url" in ev_data, "Missing url in evidence"
                print(green(f"   ✓ Evidence endpoint works"))

            # ── 9. Check list runs ───────────────────────────────────────
            print(bold("\n9. Checking run listing…"))
            runs = await client.get(f"{base}/api/runs?limit=5")
            assert runs.status_code == 200
            runs_data = runs.json()
            assert len(runs_data) > 0, "No runs in listing"
            assert any(r["id"] == run_id for r in runs_data), f"Run {run_id[:8]} not in listing"
            print(green(f"   ✓ Run appears in listing ({len(runs_data)} total)"))

        finally:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    if not failed:
        print(bold("\n" + "=" * 56))
        print(green(bold("   ✓ All E2E smoke tests passed")))
        print(bold("=" * 56))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
