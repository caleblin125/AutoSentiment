"""In-process SSE event bus — one asyncio.Queue per active run.

The SSE endpoint registers a queue before starting the agent task.
The orchestrator pushes serialised event dicts into the queue.
A None sentinel signals end-of-stream to the SSE endpoint.
"""

import asyncio

_queues: dict[str, asyncio.Queue] = {}


def register(run_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _queues[run_id] = q
    return q


def get(run_id: str) -> asyncio.Queue | None:
    return _queues.get(run_id)


def deregister(run_id: str) -> None:
    _queues.pop(run_id, None)
