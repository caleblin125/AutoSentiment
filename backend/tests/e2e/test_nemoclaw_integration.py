"""End-to-end NemoClaw interaction test.

Skipped by default because it requires a running backend, Brave quota, and local
models. Run explicitly with RUN_NEMOCLAW_E2E=1 when doing full system tests.
"""

from __future__ import annotations

import json
import os

import httpx
import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_NEMOCLAW_E2E") != "1",
    reason="Set RUN_NEMOCLAW_E2E=1 to run live NemoClaw e2e test.",
)


@pytest.mark.asyncio
async def test_nemoclaw_launches_streams_and_logs_terminal_result() -> None:
    base = os.getenv("AUTOSENTIMENT_API_URL", "http://localhost:8000").rstrip("/")
    headers = {}
    if key := os.getenv("AUTOSENTIMENT_API_KEY"):
        headers["X-API-Key"] = key

    async with httpx.AsyncClient(timeout=180.0, headers=headers) as client:
        created = (await client.post(
            f"{base}/api/runs",
            json={"topic": "NemoClaw e2e test topic", "research_depth": "quick", "use_case": "generic"},
        )).raise_for_status().json()

        run_id = created["run_id"]
        async with client.stream("GET", f"{base}/api/runs/{run_id}/events") as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    event = json.loads(line.removeprefix("data:").strip())
                    if event.get("type") in {"run_completed", "run_error", "run_cancelled"}:
                        break

        launched = (await client.post(f"{base}/api/runs/{run_id}/nemoclaw", json={})).raise_for_status().json()
        nc_run_id = launched["run_id"]
        terminal = None
        seen_events = []
        async with client.stream("GET", f"{base}/api/runs/{nc_run_id}/events") as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                event = json.loads(line.removeprefix("data:").strip())
                seen_events.append((event.get("type"), event.get("message"), event.get("detail", {})))
                if event.get("type") in {"run_completed", "run_error", "run_cancelled"}:
                    terminal = event
                    break

        assert terminal is not None
        assert seen_events, "NemoClaw should stream thoughts/progress/errors before terminal status"
        assert terminal["type"] == "run_completed", seen_events
        assert terminal.get("detail", {}).get("report", {}).get("type") == "nemoclaw"
