"""Tell an agent the one next action for a place file.

The brief reads the graph. It does not call Studio and it does not save.
"""

from __future__ import annotations

from prove.graph import Place
from prove.planner import seed_block
from prove.session import UnsupportedIntent, ensure_supported
from prove.source import latest_source
from prove.workers import missing_input

_WRITES = {"write_source", "change_and_verify"}


def brief(place: Place) -> dict:
    """One action: ``run``, ``fill``, ``plan``, ``answer``, ``blocked``, or ``done``."""
    payload = {
        "action": "done",
        "place_id": place.data["id"],
        "questions": _questions(place),
        "open_goals": [
            node["id"] for node in place.nodes() if node.get("type") == "goal" and node.get("status") == "open"
        ],
    }
    blocked = [intent for intent in place.intents() if intent.get("status") == "blocked"]
    if blocked:
        intent = blocked[0]
        payload.update(
            action="answer",
            intent=intent["id"],
            summary=_summary(intent),
            reason=str((intent.get("props") or {}).get("reason") or ""),
        )
        return payload

    nxt = place.next_intent()
    if nxt is None:
        if payload["open_goals"]:
            reason = seed_block(place)
            if reason:
                payload.update(action="blocked", reason=reason)
            else:
                payload["action"] = "plan"
        return payload

    props = nxt.get("props") or {}
    worker = props.get("worker")
    action = props.get("action")
    payload.update(intent=nxt["id"], worker=worker, intent_action=action, summary=_summary(nxt))
    try:
        ensure_supported(nxt)
    except UnsupportedIntent as exc:
        payload.update(action="blocked", reason=str(exc))
        return payload

    if action in _WRITES and payload["questions"]:
        payload["action"] = "answer"
        return payload

    missing = missing_input(nxt)
    if action == "write_source" and missing == "source":
        inputs = props.get("inputs") or {}
        path = inputs.get("path") if isinstance(inputs, dict) else None
        found = latest_source(place, path) if isinstance(path, str) and path else None
        payload.update(
            action="fill",
            path=path if isinstance(path, str) else "",
            class_name=(inputs.get("class_name") if isinstance(inputs, dict) else None),
            source=found.text if found else None,
            source_evidence=found.evidence_path if found else None,
            source_sha256=found.sha256 if found else None,
            source_bytes=len(found.text.encode("utf-8")) if found else 0,
        )
        return payload
    if missing:
        payload.update(action="blocked", reason=f"{nxt['id']} is missing inputs.{missing}")
        return payload
    payload["action"] = "run"
    return payload


def format_brief(payload: dict) -> str:
    """One fact per line. The script body stays in the JSON form."""
    lines = [f"action {payload.get('action')}", f"place {payload.get('place_id')}"]
    for key in (
        "intent",
        "worker",
        "intent_action",
        "path",
        "class_name",
        "summary",
        "reason",
        "source_evidence",
        "source_sha256",
        "source_bytes",
    ):
        value = payload.get(key)
        if value is None or value == "":
            continue
        lines.append(f"{key} {_one_line(value)}")
    questions = payload.get("questions") or []
    if questions:
        for item in questions:
            lines.append(f"question {item['id']}: {_one_line(item.get('text') or '')}")
    else:
        lines.append("questions none")
    goals = payload.get("open_goals") or []
    if goals:
        lines.append("open " + " ".join(goals))
    return "\n".join(lines)


def _questions(place: Place) -> list[dict]:
    found = []
    for node in place.nodes():
        if node.get("type") != "question" or node.get("status") != "open":
            continue
        text = (node.get("props") or {}).get("text") or node.get("name") or ""
        found.append({"id": node["id"], "text": str(text)})
    return found


def _summary(intent: dict) -> str:
    return str((intent.get("props") or {}).get("summary") or intent.get("name") or "")


def _one_line(value: object) -> str:
    return " ".join(str(value).split())
