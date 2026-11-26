"""Command line for one PROVE intent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from prove.admit import SAMPLE, add_goal, answer_question, bind_claim, fill_source, init_place
from prove.brief import brief, format_brief
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
    board = sub.add_parser("ui", help="Open the local place board. Does not call Studio.")
    board.add_argument("--host", default="127.0.0.1", help="Loopback address. Default 127.0.0.1.")
    board.add_argument("--port", type=int, default=8765, help="Port. Default 8765.")
    board.add_argument("--no-browser", action="store_true", help="Do not open a browser window.")
    nxt = sub.add_parser("next", help="Print the one next action. Does not call Studio.")
    nxt.add_argument("place", help="Path to a prove.place/1 file")
    nxt.add_argument("--json", action="store_true", help="Print the brief as JSON, including script source when filling.")
    created = sub.add_parser("init", help="Create an empty place file. Does not call Studio.")
    created.add_argument("place", help="Path to write. Use a *.local.json name.")
    created.add_argument("--id", required=True, help="Place id stored in the file.")
    created.add_argument("--title", required=True, help="Place title.")
    created.add_argument("--display-name", required=True, help="Studio window name passed to name_contains.")
    goal = sub.add_parser("goal", help="Add one goal and one claim. Does not call Studio.")
    goal.add_argument("place", help="Path to a prove.place/1 file")
    goal.add_argument("--statement", required=True, help="What the playtest has to show.")
    goal.add_argument("--contains", action="append", default=[], help="Output text the playtest must contain. Repeatable.")
    goal.add_argument("--absent", action="append", default=[], help="Output text the playtest must not contain. Repeatable.")
    goal.add_argument("--probe", action="append", default=[], help="JSON probe object with id, expression, and datamodel. Repeatable.")
    goal.add_argument("--script", help="Script path, such as game.ServerScriptService.Hello.")
    goal.add_argument("--class-name", default="Script", help="Script class when --script creates a node.")
    goal.add_argument("--seconds", type=float, default=3, help="Playtest length for the claim check.")
    goal.add_argument("--name", help="Short goal name. Defaults to the statement.")
    _add_error_flags(goal)
    bound = sub.add_parser("bind", help="Point a claim at a script or replace its check. Does not call Studio.")
    bound.add_argument("place", help="Path to a prove.place/1 file")
    bound.add_argument("claim", help="Id of the claim to update.")
    bound.add_argument("--script", help="Script path, such as game.ServerScriptService.Hello.")
    bound.add_argument("--class-name", default="Script", help="Script class when --script creates a node.")
    bound.add_argument("--contains", action="append", default=[], help="Replace expect_contains. Clears probes unless --probe is also set.")
    bound.add_argument("--absent", action="append", default=[], help="Replace expect_absent. Repeatable.")
    bound.add_argument("--probe", action="append", default=[], help="Replace probes. Clears output needles unless those flags are also set.")
    bound.add_argument("--seconds", type=float, help="Playtest length. Omit to keep the current value.")
    _add_error_flags(bound)
    planned = sub.add_parser("plan", help="Append the next intent from the latest evidence. Does not call Studio.")
    planned.add_argument("place", help="Path to a prove.place/1 file")
    filled = sub.add_parser("fill", help="Set inputs.source on the ready write intent. Does not call Studio.")
    filled.add_argument("place", help="Path to a prove.place/1 file")
    filled.add_argument("intent", help="Id of the ready write_source intent.")
    filled.add_argument("--file", required=True, help="UTF-8 file whose text becomes inputs.source.")
    answered = sub.add_parser("answer", help="Record an answer on an open question. Does not call Studio.")
    answered.add_argument("place", help="Path to a prove.place/1 file")
    answered.add_argument("question", help="Id of the open question.")
    answered.add_argument("--text", required=True, help="The person's answer.")
    run = sub.add_parser("run", help="Run the next ready intent against the open Studio window.")
    run.add_argument("place", help="Path to a prove.place/1 file")
    run.add_argument("--name", help="Studio window whose name contains this text. Overrides identity.display_name.")
    run.add_argument("--studio-id", help="Studio window id from list_roblox_studios.")
    run.add_argument("--json", action="store_true", help="Print the worker result JSON.")
    args = parser.parse_args(argv)
    if args.command == "ui":
        from prove.ui import run_ui

        try:
            run_ui(args.host, args.port, open_browser=not args.no_browser)
        except PlaceError as exc:
            print(exc, file=sys.stderr)
            return 2
        return 0
    if args.command == "init":
        try:
            init_place(args.place, args.id, args.title, args.display_name)
        except PlaceError as exc:
            print(exc, file=sys.stderr)
            return 2
        print(f"created {args.place}")
        return 0
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
    if args.command == "next":
        try:
            payload = brief(place)
        except PlaceError as exc:
            print(exc, file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(format_brief(payload))
        return 2 if payload.get("action") in {"answer", "blocked"} else 0
    if args.command == "plan":
        try:
            outcome = plan(place)
        except PlaceError as exc:
            print(exc, file=sys.stderr)
            return 2
        print("\n".join(outcome.lines))
        return outcome.code
    if Path(args.place).name == "example.place.json":
        print(SAMPLE, file=sys.stderr)
        return 2
    if args.command == "goal":
        try:
            lines = add_goal(
                place,
                statement=args.statement,
                contains=args.contains,
                absent=args.absent,
                script=args.script,
                class_name=args.class_name,
                seconds=args.seconds,
                name=args.name,
                probes=_parse_probes(args.probe),
                forbid_errors=_forbid_errors(args),
            )
            place.save()
        except PlaceError as exc:
            print(exc, file=sys.stderr)
            return 2
        print("\n".join(lines))
        return 0
    if args.command == "bind":
        try:
            lines = bind_claim(
                place,
                args.claim,
                script=args.script,
                class_name=args.class_name,
                contains=args.contains or None,
                absent=args.absent or None,
                probes=_parse_probes(args.probe),
                seconds=args.seconds,
                forbid_errors=_forbid_errors(args),
            )
            place.save()
        except PlaceError as exc:
            print(exc, file=sys.stderr)
            return 2
        print("\n".join(lines))
        return 0
    if args.command == "fill":
        try:
            source = Path(args.file).read_text(encoding="utf-8")
            fill_source(place, args.intent, source)
            place.save()
        except (OSError, UnicodeError) as exc:
            print(exc, file=sys.stderr)
            return 2
        except PlaceError as exc:
            print(exc, file=sys.stderr)
            return 2
        print(f"filled {args.intent}")
        return 0
    if args.command == "answer":
        try:
            answer_question(place, args.question, args.text)
            place.save()
        except PlaceError as exc:
            print(exc, file=sys.stderr)
            return 2
        print(f"answered {args.question}")
        return 0
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


def _add_error_flags(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--forbid-errors", action="store_true", help="Fail the playtest when Output has an error.")
    group.add_argument("--allow-errors", action="store_true", help="Ignore Output errors. Probe-only checks do this unless --forbid-errors is set.")


def _forbid_errors(args: argparse.Namespace) -> bool | None:
    if args.forbid_errors:
        return True
    if args.allow_errors:
        return False
    return None


def _parse_probes(raw: list[str] | None) -> list[dict] | None:
    if not raw:
        return None
    probes = []
    for text in raw:
        try:
            item = json.loads(text)
        except json.JSONDecodeError as exc:
            raise PlaceError(f"Probe is not JSON: {exc}") from exc
        if not isinstance(item, dict):
            raise PlaceError("A probe is a JSON object")
        probes.append(item)
    return probes


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
