#!/usr/bin/env python3
"""Terminal UI for AutoSentiment.

Uses only the Python standard library so it works inside the backend venv
without installing a curses/textual dependency. Set AUTOSENTIMENT_API_URL and
AUTOSENTIMENT_API_KEY when the backend is not using the defaults.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_API_URL = "http://localhost:8000"


@dataclass(frozen=True)
class ClientConfig:
    base_url: str
    api_key: str | None = None


def parse_sse_lines(lines: Iterable[str]) -> Iterable[dict]:
    """Yield JSON events from a text/event-stream response."""
    buffer: list[str] = []
    for raw_line in lines:
        line = raw_line.rstrip("\r\n")
        if not line:
            if buffer:
                payload = "\n".join(buffer)
                buffer.clear()
                try:
                    yield json.loads(payload)
                except json.JSONDecodeError:
                    continue
            continue
        if line.startswith("data:"):
            buffer.append(line[5:].strip())
    if buffer:
        try:
            yield json.loads("\n".join(buffer))
        except json.JSONDecodeError:
            return


def format_pct(value: float | int | None) -> str:
    if not isinstance(value, (int, float)):
        return "0%"
    return f"{round(value * 100)}%"


def format_run_row(run: dict) -> str:
    overall = run.get("overall") or {}
    score = (
        f"+{format_pct(overall.get('positive'))} "
        f"~{format_pct(overall.get('neutral'))} "
        f"-{format_pct(overall.get('negative'))}"
        if overall else "no report"
    )
    return f"{run.get('id', '')[:8]:8}  {run.get('status', '?'):10}  {score:22}  {run.get('topic', '')}"


def format_report(report: dict) -> str:
    overall = report.get("overall") or {}
    themes = report.get("themes") or []
    lines = [
        f"Items: {overall.get('total', 0)}",
        f"Sentiment: +{format_pct(overall.get('positive'))} ~{format_pct(overall.get('neutral'))} -{format_pct(overall.get('negative'))}",
    ]
    if themes:
        lines.append(f"Themes: {', '.join(str(t) for t in themes[:8])}")
    narrative = report.get("narrative")
    if narrative:
        lines.extend(["", str(narrative)])
    timeline = report.get("timeline") or {}
    if timeline.get("event_summary"):
        lines.extend(["", f"Chronology: {timeline['event_summary']}"])
    return "\n".join(lines)


def _request(config: ClientConfig, method: str, path: str, body: dict | None = None):
    url = f"{config.base_url.rstrip('/')}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if config.api_key:
        headers["X-API-Key"] = config.api_key
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=120) as response:
            content_type = response.headers.get("Content-Type", "")
            if "text/event-stream" in content_type:
                for event in parse_sse_lines(line.decode("utf-8", "replace") for line in response):
                    yield event
            else:
                payload = response.read().decode("utf-8")
                yield json.loads(payload) if payload else {}
    except HTTPError as exc:
        raise SystemExit(f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')}") from exc
    except URLError as exc:
        raise SystemExit(f"Connection failed: {exc.reason}") from exc


def request_json(config: ClientConfig, method: str, path: str, body: dict | None = None) -> dict | list:
    return next(_request(config, method, path, body))


def stream_events(config: ClientConfig, run_id: str) -> None:
    for event in _request(config, "GET", f"/api/runs/{run_id}/events"):
        event_type = event.get("type", "?")
        message = event.get("message", "")
        detail = event.get("detail") or {}
        if event_type == "item_analyzed":
            print(f"{event_type:17} {detail.get('label', ''):8} {message}")
        else:
            print(f"{event_type:17} {message}")
        if event_type in {"run_completed", "run_cancelled", "run_error"}:
            break


def cmd_list(config: ClientConfig, args: argparse.Namespace) -> None:
    runs = request_json(config, "GET", f"/api/runs?limit={args.limit}")
    print("ID        STATUS      SENTIMENT               TOPIC")
    for run in runs if isinstance(runs, list) else []:
        print(format_run_row(run))


def cmd_run(config: ClientConfig, args: argparse.Namespace) -> None:
    body = {
        "topic": args.topic,
        "research_depth": args.depth,
        "use_case": args.use_case,
    }
    if args.freshness:
        body["freshness"] = args.freshness
    created = request_json(config, "POST", "/api/runs", body)
    run_id = str(created["run_id"])
    print(f"Started {run_id}")
    if args.stream:
        stream_events(config, run_id)


def cmd_show(config: ClientConfig, args: argparse.Namespace) -> None:
    run = request_json(config, "GET", f"/api/runs/{args.run_id}")
    report = run.get("report") if isinstance(run, dict) else None
    print(f"{run.get('topic', args.run_id)} [{run.get('status', '?')}]" if isinstance(run, dict) else args.run_id)
    print()
    print(format_report(report or {}))


def cmd_cancel(config: ClientConfig, args: argparse.Namespace) -> None:
    result = request_json(config, "POST", f"/api/runs/{args.run_id}/cancel", {})
    print(json.dumps(result, indent=2))


def interactive(config: ClientConfig) -> None:
    print("AutoSentiment TUI. Commands: list, run <topic>, show <run_id>, stream <run_id>, cancel <run_id>, quit")
    while True:
        try:
            line = input("autosentiment> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line:
            continue
        if line in {"quit", "exit"}:
            return
        parts = line.split(maxsplit=1)
        command, rest = parts[0], parts[1] if len(parts) > 1 else ""
        try:
            if command == "list":
                cmd_list(config, argparse.Namespace(limit=20))
            elif command == "run" and rest:
                cmd_run(config, argparse.Namespace(topic=rest, depth="standard", use_case="generic", freshness="pm", stream=True))
            elif command == "show" and rest:
                cmd_show(config, argparse.Namespace(run_id=rest))
            elif command == "stream" and rest:
                stream_events(config, rest)
            elif command == "cancel" and rest:
                cmd_cancel(config, argparse.Namespace(run_id=rest))
            else:
                print("Unknown command or missing argument.")
        except SystemExit as exc:
            print(exc, file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AutoSentiment terminal UI")
    parser.add_argument("--api-url", default=os.getenv("AUTOSENTIMENT_API_URL", DEFAULT_API_URL))
    parser.add_argument("--api-key", default=os.getenv("AUTOSENTIMENT_API_KEY"))
    sub = parser.add_subparsers(dest="command")

    list_p = sub.add_parser("list", help="List recent runs")
    list_p.add_argument("--limit", type=int, default=20)

    run_p = sub.add_parser("run", help="Start a run")
    run_p.add_argument("topic")
    run_p.add_argument("--depth", default="standard", choices=["quick", "standard", "deep", "exhaustive"])
    run_p.add_argument("--use-case", default="generic")
    run_p.add_argument("--freshness", default="pm", choices=["", "pd", "pw", "pm", "py"])
    run_p.add_argument("--no-stream", action="store_false", dest="stream")

    show_p = sub.add_parser("show", help="Show one run report")
    show_p.add_argument("run_id")

    stream_p = sub.add_parser("stream", help="Stream run events")
    stream_p.add_argument("run_id")

    cancel_p = sub.add_parser("cancel", help="Cancel a run")
    cancel_p.add_argument("run_id")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = ClientConfig(base_url=args.api_url, api_key=args.api_key)
    if args.command == "list":
        cmd_list(config, args)
    elif args.command == "run":
        cmd_run(config, args)
    elif args.command == "show":
        cmd_show(config, args)
    elif args.command == "stream":
        stream_events(config, args.run_id)
    elif args.command == "cancel":
        cmd_cancel(config, args)
    else:
        interactive(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
