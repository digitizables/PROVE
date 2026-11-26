"""Command line for one PROVE intent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from prove.graph import Place, PlaceError
from prove.planner import plan
from prove.records import envelope, worker_result
from prove.session import (
    UnsupportedIntent,
    begin,
    complete,
    ensure_supported,
    evidence_paths,
    run_intent,
)
from prove.workers import NeedPerson, _settle, require_ready


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    parser = argparse.ArgumentParser(prog="prove", description="Plan or run one PROVE intent and record the evidence.")
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status", help="Show the active intent, the next intent, and open questions.")
    status.add_argument("place", help="Path to a prove.place/1 file")
    planned = sub.add_parser("plan", help="Append the next intent from the latest evidence. Does not call Studio.")
    planned.add_argument("place", help="Path to a prove.place/1 file")
    run = sub.add_parser("run", help="Run the next ready intent against the open Studio window.")
    run.add_argument("place", help="Path to a prove.place/1 file")
    run.add_argument("--name", help="Studio window whose name contains this text. Overrides identity.display_name.")
    run.add_argument("--studio-id", help="Studio window id from list_roblox_studios.")
    run.add_argument("--json", action="store_true", help="Print the worker result JSON.")
    args = parser.parse_args(argv)
    try:
        place = Place.load(args.place)
    except PlaceError as exc:
        print(exc, file=sys.stderr)
        return 2
    if args.command == "status":
        try:
            print(format_status(place))
        except PlaceError as exc:
            print(exc, file=sys.stderr)
            return 2
        return 0
    if args.command == "plan":
        try:
            outcome = plan(place)
        except PlaceError as exc:
            print(exc, file=sys.stderr)
            return 2
        print("\n".join(outcome.lines))
        return outcome.code
    if Path(args.place).name == "example.place.json":
        print(
            "Copy this sample to graph/places/<id>.local.json and run that file. "
            "The checked-in example stays unchanged.",
            file=sys.stderr,
        )
        return 2
    try:
        result = run_studio(place, name=args.name, studio_id=args.studio_id)
    except UnsupportedIntent as exc:
        print(exc, file=sys.stderr)
        return 2
    except NeedPerson as exc:
        print(exc, file=sys.stderr)
        return 2
    except PlaceError as exc:
        print(exc, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        evidence = result["evidence"]
        print(f"{result['intent_id']} {evidence['verdict']}: {evidence['summary']}")
        for node in result["graph_patch"]["upsert_nodes"]:
            if node.get("type") == "evidence":
                print(node["props"].get("path", ""))
    verdict = result["evidence"]["verdict"]
    if verdict in {"pass", "inconclusive"}:
        return 0
    if verdict == "fail":
        return 1
    return 2


def format_status(place: Place) -> str:
    lines = [f"place {place.data['id']}"]
    active = place.active_intent()
    lines.append("active " + (active["id"] if active else "none"))
    nxt = place.next_intent()
    if nxt is None:
        lines.append("next none")
    else:
        props = nxt.get("props") or {}
        lines.append(f"next {nxt['id']} {props.get('worker')} {props.get('action')} ({nxt['status']})")
    done = {item["id"] for item in place.intents() if item.get("status") == "done"}
    for intent in place.intents():
        if intent.get("status") != "proposed":
            continue
        after = (intent.get("props") or {}).get("after")
        if after and after not in done:
            lines.append(f"waiting {intent['id']} after {after}")
    for question in place.nodes():
        if question.get("type") == "question" and question.get("status") == "open":
            text = (question.get("props") or {}).get("text") or question.get("name")
            lines.append(f"question {question['id']}: {text}")
    return "\n".join(lines)


def run_studio(place: Place, *, name: str | None, studio_id: str | None) -> dict:
    from roblox_studio_adapter import RobloxStudio
    from roblox_studio_adapter.errors import AmbiguousStudioError, NoStudioError

    intent = place.next_intent()
    if intent is None:
        raise PlaceError("No proposed intent is ready")
    ensure_supported(intent)
    require_ready(intent)
    selector: dict[str, str] = {}
    if studio_id:
        selector["studio_id"] = studio_id
    elif name:
        selector["name_contains"] = name
    else:
        display = (place.data.get("identity") or {}).get("display_name")
        if isinstance(display, str) and display:
            selector["name_contains"] = display
    try:
        opened = RobloxStudio.connect(**selector)
    except (AmbiguousStudioError, NoStudioError) as exc:
        locked = begin(place)
        _absolute, stored = evidence_paths(place, locked, None)
        evidence = envelope(
            intent_id=locked["id"],
            place_id=str(place.data["id"]),
            worker=str(locked["props"].get("worker")),
            verdict="blocked",
            summary=str(exc),
            limits="Choose the Studio window and run this intent again.",
            observations=[{"kind": "session", "text": str(exc)}],
        )
        nodes, edges, statuses = _settle(place, locked, evidence, stored)
        result = worker_result(intent_id=locked["id"], evidence=evidence, nodes=nodes, edges=edges, statuses=statuses)
        return complete(place, result)
    with opened as agent:
        return run_intent(place, agent)
