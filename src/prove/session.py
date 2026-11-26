"""Run one ready intent and persist its worker result."""

from __future__ import annotations

import json
import re
from pathlib import Path

from prove.graph import Place, PlaceError
from prove.records import envelope, worker_result
from prove.workers import NeedPerson, change_and_verify, overview, read_source, verify_output, write_source

IMPLEMENTED = {
    ("script", "read_source"): read_source,
    ("script", "write_source"): write_source,
    ("playtest", "verify_output"): verify_output,
    ("playtest", "change_and_verify"): change_and_verify,
    ("explore", "overview"): overview,
}


class UnsupportedIntent(PlaceError):
    """This runtime has no handler for the intent's worker and action."""


def ensure_supported(intent: dict) -> None:
    props = intent.get("props") or {}
    key = (props.get("worker"), props.get("action"))
    if key not in IMPLEMENTED:
        raise UnsupportedIntent(f"{intent.get('id')} needs {key[0]} {key[1]}, which this runtime does not run")


def begin(place: Place) -> dict:
    """Lock the next intent as active and save that lock before any Studio call."""
    intent = place.next_intent()
    if intent is None:
        raise PlaceError("No proposed intent is ready")
    ensure_supported(intent)
    if intent["status"] == "proposed":
        place.activate(intent["id"])
        place.save()
    return intent


def run_intent(place: Place, agent: object, *, runs_dir: Path | None = None) -> dict:
    intent = begin(place)
    _absolute, stored = evidence_paths(place, intent, runs_dir)
    try:
        result = IMPLEMENTED[(intent["props"]["worker"], intent["props"]["action"])](place, agent, intent, stored)
    except NeedPerson as exc:
        result = _terminal(place, intent, stored, verdict="blocked", summary=str(exc), limits="The person has to edit this intent.")
    except Exception as exc:
        mapped = _map_adapter_error(place, intent, stored, exc)
        if mapped is None:
            raise
        result = mapped
    return complete(place, result, runs_dir=runs_dir)


def complete(place: Place, result: dict, *, runs_dir: Path | None = None) -> dict:
    intent = place.node(result["intent_id"])
    if intent is None:
        raise PlaceError(f"Result names missing intent {result['intent_id']}")
    absolute, _stored = evidence_paths(place, intent, runs_dir)
    absolute.parent.mkdir(parents=True, exist_ok=True)
    absolute.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    place.apply_patch(result["graph_patch"])
    place.add_follow_ups(result.get("follow_ups") or [])
    place.close_goals()
    place.save()
    return result


def evidence_paths(place: Place, intent: dict, runs_dir: Path | None) -> tuple[Path, str]:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", intent["id"]).strip("-") or "intent"
    filename = f"{safe}.worker-result.json"
    root = locate_root(place.path)
    if runs_dir is not None:
        absolute = Path(runs_dir) / filename
        if root is not None:
            try:
                stored = absolute.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                stored = absolute.resolve().as_posix()
        else:
            stored = absolute.resolve().as_posix()
        return absolute, stored
    if root is not None:
        return root / "evidence" / "runs" / filename, f"evidence/runs/{filename}"
    folder = place.path.parent / "evidence-runs"
    return folder / filename, (folder / filename).resolve().as_posix()


def locate_root(start: Path) -> Path | None:
    for candidate in [start.parent, *start.parents]:
        if (candidate / "AGENTS.md").is_file() and (candidate / "protocols").is_dir():
            return candidate
    return None


def _map_adapter_error(place: Place, intent: dict, stored: str, exc: Exception) -> dict | None:
    try:
        from roblox_studio_adapter.errors import (
            AmbiguousOutcome,
            AmbiguousStudioError,
            ModeError,
            NeedsUserAction,
            NoStudioError,
            PermissionDenied,
            TimeoutError,
            ToolFailed,
            UnyieldingLuau,
        )
    except ImportError:
        return None
    if isinstance(exc, (AmbiguousStudioError, NoStudioError, NeedsUserAction, PermissionDenied)):
        return _terminal(place, intent, stored, verdict="blocked", summary=str(exc), limits="Stopped for the person.")
    if isinstance(exc, (AmbiguousOutcome, TimeoutError)):
        tool = getattr(exc, "tool", "call")
        return _terminal(
            place,
            intent,
            stored,
            verdict="inconclusive",
            summary=str(exc),
            limits="The call may already have changed the place. Read it before repeating the call.",
            follow_ups=[_readback(intent, str(tool))],
        )
    if isinstance(exc, (ToolFailed, ModeError, UnyieldingLuau)):
        return _terminal(place, intent, stored, verdict="fail", summary=str(exc), limits="The Studio call reported failure.")
    return None


def _terminal(
    place: Place,
    intent: dict,
    stored: str,
    *,
    verdict: str,
    summary: str,
    limits: str,
    follow_ups: list[dict] | None = None,
) -> dict:
    evidence = envelope(
        intent_id=intent["id"],
        place_id=str(place.data["id"]),
        worker=str((intent.get("props") or {}).get("worker") or "session"),
        verdict=verdict,
        summary=summary,
        limits=limits,
        observations=[{"kind": "session", "text": summary[:500]}],
    )
    from prove.workers import _settle

    nodes, edges, statuses = _settle(place, intent, evidence, stored)
    return worker_result(
        intent_id=intent["id"],
        evidence=evidence,
        nodes=nodes,
        edges=edges,
        statuses=statuses,
        follow_ups=follow_ups,
    )


def _readback(intent: dict, tool: str) -> dict:
    props = intent.get("props") or {}
    inputs = props.get("inputs") or {}
    path = inputs.get("path")
    if not isinstance(path, str) or path == "":
        scripts = inputs.get("scripts") or []
        if scripts and isinstance(scripts[0], dict):
            path = scripts[0].get("path")
    order = props.get("order")
    if not isinstance(order, int):
        order = 1
    if isinstance(path, str) and path:
        worker = "script"
        action = "read_source"
        follow_inputs: dict = {"path": path}
        summary = f"Read back {path} after an ambiguous {tool}."
    else:
        worker = "explore"
        action = "overview"
        follow_inputs = {}
        summary = f"Explore again after an ambiguous {tool}."
    return {
        "id": f"{intent['id']}-readback",
        "type": "intent",
        "name": "Read back",
        "status": "proposed",
        "props": {
            "goal_id": props.get("goal_id") or "goal:unknown",
            "worker": worker,
            "action": action,
            "summary": summary[:200],
            "inputs": follow_inputs,
            "done_when": "The place has been read after the call that may have landed.",
            "must_not": ["Repeat the call that may have landed.", "Save the place."],
            "after": None,
            "order": order + 1,
        },
    }
