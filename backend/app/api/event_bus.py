"""In-process SSE event bus — one asyncio.Queue per active run.

Cancellation uses two mechanisms:
 1. Cooperative flag (_cancelled_runs) — checked at stage boundaries and
    between every streamed LLM token via cancel_check callbacks.
 2. HTTP-level timeouts — Brave search and fetch calls are wrapped with
    asyncio.wait_for so they can be interrupted promptly on cancel.
"""

import asyncio

_queues: dict[str, asyncio.Queue] = {}
_cancelled_runs: set[str] = set()


def register(run_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _queues[run_id] = q
    return q


def get(run_id: str) -> "asyncio.Queue | None":
    return _queues.get(run_id)


def deregister(run_id: str) -> None:
    _queues.pop(run_id, None)


def request_cancel(run_id: str) -> None:
    """Signal cooperative cancellation; checked at every LLM token and stage boundary."""
    _cancelled_runs.add(run_id)


def is_cancelled(run_id: str) -> bool:
    return run_id in _cancelled_runs


def clear_cancel(run_id: str) -> None:
    _cancelled_runs.discard(run_id)
