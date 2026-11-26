"""Append the next intent from the latest evidence.

The rules are docs/playbooks/iterate-on-failure.md and planner/README.md.
This module does not call Studio and does not activate an intent.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path

from prove.graph import Place, script_key, slug
from prove.records import evidence_id_for
from prove.session import locate_root

_VERIFY_ACTIONS = {"verify_output", "change_and_verify"}
_SAMPLE = (
    "Copy this sample to graph/places/<id>.local.json and plan that file. "
    "The checked-in example stays unchanged."
)


@dataclass
class PlanResult:
    changed: bool
    code: int
    lines: list[str]


@dataclass
class _Record:
    intent: dict
    evidence: dict
    studio: dict
    kind: str
    claims: list[str]

    @property
    def rank(self) -> tuple:
        return _rank(self.intent)


def plan(place: Place) -> PlanResult:
    """Update ``place`` from its latest evidence and save when the graph changes."""
    original = copy.deepcopy(place.data)
    code, lines = _decide(place)
    changed = place.data != original
    if changed and place.path.name == "example.place.json":
        place.data = original
        return PlanResult(False, 2, [_SAMPLE])
    if changed:
        place.save()
    return PlanResult(changed, code, lines)


def _decide(place: Place) -> tuple[int, list[str]]:
    lines: list[str] = []
    before = {node["id"]: node.get("status") for node in place.nodes() if node.get("type") == "goal"}
    place.close_goals()
    for goal in place.nodes():
        if goal.get("type") == "goal" and before.get(goal["id"]) != goal.get("status"):
            lines.append(f"{goal['id']} done")

    blocked = [intent for intent in place.intents() if intent.get("status") == "blocked"]
    if blocked:
        intent = blocked[0]
        summary = str((intent.get("props") or {}).get("summary") or intent.get("name") or "")
        lines.append(f"blocked {intent['id']}: {summary}")
        return 2, lines

    nxt = place.next_intent()
    if nxt is not None:
        lines.append(_next_line(nxt))
        return 0, lines

    candidates: list[tuple[dict, _Record]] = []
    missing: list[str] = []
    for goal in place.nodes():
        if goal.get("type") != "goal" or goal.get("status") != "open":
            continue
        waiting = _proposed_for(place, goal["id"])
        if waiting is not None:
            lines.append(_next_line(waiting))
            return 0, lines
        found, error = _latest_verify(place, goal["id"])
        if error:
            missing.append(error)
            continue
        if found is not None and found.kind in {"fail", "reset"}:
            candidates.append((goal, found))

    if candidates:
        goal, found = max(candidates, key=lambda item: item[1].rank)
        return _follow(place, goal, found, lines)

    if missing:
        lines.append(missing[0])
        return 2, lines
    lines.append("nothing to add")
    return 0, lines


def _follow(place: Place, goal: dict, found: _Record, lines: list[str]) -> tuple[int, list[str]]:
    if found.kind == "reset":
        added = _append_replay(place, goal, found)
        lines.extend(added)
        return 0, lines
    if _same_failure_count(place, found) >= 3:
        lines.extend(_stop_for_person(place, goal, found))
        return 2, lines
    lines.extend(_append_fix(place, goal, found))
    return 0, lines


def _append_replay(place: Place, goal: dict, found: _Record) -> list[str]:
    label = _check_ids(found.studio) or "the previous playtest"
    summary = _clip(f"console.reset on {found.intent['id']}. Snapshot Output again for {label}.")
    intent = _intent(
        place,
        stem=f"intent:replay-{slug(_primary_check_id(found))}",
        name="Snapshot Output again",
        goal_id=goal["id"],
        worker="playtest",
        action="verify_output",
        summary=summary,
        inputs=_verify_inputs(found.intent),
        done_when=_done_when(found.intent, f"Evidence verdict is pass for {label}."),
        must_not=_must_not(found.intent, ["Edit any script.", "Save the place.", "Publish."]),
        after=None,
        order=_next_order(place),
    )
    place.add_follow_ups([intent])
    _link_checks(place, intent["id"], found.claims)
    return [f"added {intent['id']} playtest verify_output"]


def _append_fix(place: Place, goal: dict, found: _Record) -> list[str]:
    check_id, quote = _failure_label(found)
    node, path = _target(place, goal["id"], found)
    order = _next_order(place)
    previous: str | None = None
    batch: list[dict] = []
    lines: list[str] = []
    if path is None:
        look = _intent(
            place,
            stem=f"intent:look-{slug(check_id)}",
            name="Explore after failure",
            goal_id=goal["id"],
            worker="explore",
            action="overview",
            summary=_clip(f"{quote}. No script path is on the graph. Explore the place."),
            inputs={},
            done_when="Services and scripts from the explore are observed.",
            must_not=["Write a script.", "Start a playtest.", "Save the place."],
            after=None,
            order=order,
        )
        batch.append(look)
        previous = look["id"]
        order += 1
        lines.append(f"added {look['id']} explore overview")
    elif _needs_read(node):
        read = _intent(
            place,
            stem=f"intent:read-{slug(check_id)}",
            name="Read before fix",
            goal_id=goal["id"],
            worker="script",
            action="read_source",
            summary=_clip(f"{quote}. Read {path}."),
            inputs={"path": path},
            done_when="The script status is observed and props.source_sha256 is set.",
            must_not=["Write the script.", "Start a playtest.", "Save the place."],
            after=None,
            order=order,
        )
        batch.append(read)
        previous = read["id"]
        order += 1
        lines.append(f"added {read['id']} script read_source")
    write_inputs: dict = {"path": path or ""}
    class_name = (node or {}).get("props", {}).get("class_name") if node else None
    if isinstance(class_name, str) and class_name:
        write_inputs["class_name"] = class_name
    if path is not None:
        write = _intent(
            place,
            stem=f"intent:fix-{slug(check_id)}",
            name=f"Fix {check_id}",
            goal_id=goal["id"],
            worker="script",
            action="write_source",
            summary=_clip(f"{quote}. Write {path}."),
            inputs=write_inputs,
            done_when="The script source is written and source_sha256 is updated.",
            must_not=["Start a playtest.", "Save the place.", "Publish."],
            after=previous,
            order=order,
        )
        batch.append(write)
        previous = write["id"]
        order += 1
        lines.append(f"added {write['id']} script write_source")
    recheck = _intent(
        place,
        stem=f"intent:recheck-{slug(check_id)}",
        name="Verify again",
        goal_id=goal["id"],
        worker="playtest",
        action="verify_output",
        summary=_clip(f"Re-check {check_id} after the fix."),
        inputs=_verify_inputs(found.intent),
        done_when=_done_when(found.intent, f"Evidence verdict is pass for {check_id}."),
        must_not=_must_not(found.intent, ["Edit any script.", "Save the place.", "Publish."]),
        after=previous,
        order=order,
    )
    batch.append(recheck)
    place.add_follow_ups(batch)
    _link_checks(place, recheck["id"], found.claims)
    if previous and recheck["props"]["after"]:
        lines.append(f"waiting {recheck['id']} after {recheck['props']['after']}")
    else:
        lines.append(f"added {recheck['id']} playtest verify_output")
    return lines


def _stop_for_person(place: Place, goal: dict, found: _Record) -> list[str]:
    check_id, quote = _failure_label(found)
    claim = found.claims[0] if found.claims else goal["id"]
    question_id = _fresh(place, f"question:{slug(claim.removeprefix('claim:'))}-stuck")
    text = _clip(f"{claim} failed 3 times with the same observation ({quote}). What should change?", 500)
    question = {
        "id": question_id,
        "type": "question",
        "name": "Same failure",
        "status": "open",
        "props": {"text": text},
    }
    summary = _clip(f"Stopped after 3 failures with the same observation ({check_id}). Answer {question_id}.")
    intent = _intent(
        place,
        stem=f"intent:stop-{slug(check_id)}",
        name="Stop after repeated failure",
        goal_id=goal["id"],
        worker="playtest",
        action="verify_output",
        summary=summary,
        inputs=_verify_inputs(found.intent),
        done_when="The person answered the question.",
        must_not=["Repeat the playtest until the question is answered.", "Save the place."],
        after=None,
        order=_next_order(place),
    )
    intent["status"] = "blocked"
    intent["props"]["reason"] = "Three failures with the same observation."
    place.nodes().append(question)
    place.nodes().append(intent)
    place.data["edges"].append(
        {"id": f"edge:{intent['id']}:goal", "type": "spawned_from", "from": intent["id"], "to": goal["id"]}
    )
    target = _about_target(place, found, goal["id"])
    if target is not None:
        place.data["edges"].append(
            {"id": f"edge:{question_id}:about", "type": "about", "from": question_id, "to": target}
        )
    place._assert_graph()
    return [f"blocked {intent['id']}: {summary}", f"question {question_id}: {text}"]


def _latest_verify(place: Place, goal_id: str) -> tuple[_Record | None, str | None]:
    verifies = [
        intent
        for intent in _goal_intents(place, goal_id)
        if intent.get("status") == "done" and _is_verify(intent)
    ]
    if not verifies:
        return None, None
    latest = max(verifies, key=_rank)
    evidence = _load_evidence(place, latest["id"])
    if evidence is None:
        return None, f"missing evidence file for {latest['id']}"
    studio = evidence.get("studio") if isinstance(evidence.get("studio"), dict) else {}
    return (
        _Record(
            intent=latest,
            evidence=evidence,
            studio=studio,
            kind=_kind(evidence, studio),
            claims=place.claims_checked_by(latest["id"]),
        ),
        None,
    )


def _same_failure_count(place: Place, found: _Record) -> int:
    key = _signature(found.studio)
    count = 0
    intents = place.intents()
    if found.claims:
        intents = [intent for intent in intents if any(claim in found.claims for claim in place.claims_checked_by(intent["id"]))]
    for intent in intents:
        if intent.get("status") != "done" or not _is_verify(intent):
            continue
        evidence = _load_evidence(place, intent["id"])
        if evidence is None or evidence.get("verdict") != "fail":
            continue
        studio = evidence.get("studio") if isinstance(evidence.get("studio"), dict) else {}
        if _kind(evidence, studio) == "fail" and _signature(studio) == key:
            count += 1
    return count


def _target(place: Place, goal_id: str, found: _Record) -> tuple[dict | None, str | None]:
    linked = _linked_scripts(place, found.claims)
    for node in linked:
        path = _node_path(node)
        if path:
            return node, path
    for intent in sorted(_goal_intents(place, goal_id), key=_rank, reverse=True):
        for path in _paths_from_intent(intent):
            node = place.find_script(path)
            return node, "game." + script_key(path)
    for node in place.nodes():
        if node.get("type") != "script":
            continue
        path = _node_path(node)
        if path:
            return node, path
    if linked:
        return linked[0], None
    return None, None


def _linked_scripts(place: Place, claims: list[str]) -> list[dict]:
    systems = {
        edge.get("to")
        for edge in place.data["edges"]
        if edge.get("type") == "about" and edge.get("from") in claims
    }
    script_ids = [
        edge.get("from")
        for edge in place.data["edges"]
        if edge.get("type") == "implements" and edge.get("to") in systems
    ]
    nodes = []
    for script_id in script_ids:
        node = place.node(str(script_id))
        if node is not None and node.get("type") == "script":
            nodes.append(node)
    return nodes


def _load_evidence(place: Place, intent_id: str) -> dict | None:
    node = place.node(evidence_id_for(intent_id))
    if node is None or node.get("type") != "evidence":
        return None
    stored = (node.get("props") or {}).get("path")
    if not isinstance(stored, str) or stored == "":
        return None
    path = _resolve(place, stored)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    evidence = data.get("evidence")
    if isinstance(evidence, dict):
        return evidence
    if data.get("schema") == "prove.evidence/1":
        return data
    return None


def _resolve(place: Place, stored: str) -> Path:
    raw = Path(stored)
    if raw.is_file():
        return raw
    root = locate_root(place.path)
    if root is not None:
        candidate = root / stored
        if candidate.is_file():
            return candidate
    return place.path.parent / stored


def _intent(
    place: Place,
    *,
    stem: str,
    name: str,
    goal_id: str,
    worker: str,
    action: str,
    summary: str,
    inputs: dict,
    done_when: str,
    must_not: list[str],
    after: str | None,
    order: int,
) -> dict:
    return {
        "id": _fresh(place, stem),
        "type": "intent",
        "name": name[:80],
        "status": "proposed",
        "props": {
            "goal_id": goal_id,
            "worker": worker,
            "action": action,
            "summary": summary,
            "inputs": inputs,
            "done_when": done_when,
            "must_not": must_not,
            "after": after,
            "order": order,
        },
    }


def _link_checks(place: Place, intent_id: str, claims: list[str]) -> None:
    for claim_id in claims:
        if place.node(claim_id) is None:
            continue
        edge_id = f"edge:{intent_id}:checks:{claim_id}"
        if any(edge.get("id") == edge_id for edge in place.data["edges"]):
            continue
        place.data["edges"].append({"id": edge_id, "type": "checks", "from": intent_id, "to": claim_id})
    place._assert_graph()


def _goal_intents(place: Place, goal_id: str) -> list[dict]:
    ids = [
        edge.get("from")
        for edge in place.data["edges"]
        if edge.get("type") == "spawned_from" and edge.get("to") == goal_id
    ]
    found: list[dict] = []
    seen: set[str] = set()
    for intent_id in ids:
        node = place.node(str(intent_id))
        if node is not None and node.get("type") == "intent" and node["id"] not in seen:
            found.append(node)
            seen.add(node["id"])
    for intent in place.intents():
        if (intent.get("props") or {}).get("goal_id") == goal_id and intent["id"] not in seen:
            found.append(intent)
            seen.add(intent["id"])
    return found


def _proposed_for(place: Place, goal_id: str) -> dict | None:
    proposed = [intent for intent in _goal_intents(place, goal_id) if intent.get("status") == "proposed"]
    if not proposed:
        return None
    return min(proposed, key=_rank)


def _verify_inputs(intent: dict) -> dict:
    inputs = (intent.get("props") or {}).get("inputs") or {}
    if not isinstance(inputs, dict):
        return {}
    kept = {}
    for key in ("seconds", "screenshot", "expect_contains", "expect_absent", "forbid_errors", "probes"):
        if key in inputs:
            kept[key] = copy.deepcopy(inputs[key])
    return kept


def _paths_from_intent(intent: dict) -> list[str]:
    inputs = (intent.get("props") or {}).get("inputs") or {}
    if not isinstance(inputs, dict):
        return []
    found = []
    path = inputs.get("path")
    if isinstance(path, str) and path:
        found.append(path)
    for item in inputs.get("scripts") or []:
        if isinstance(item, dict) and isinstance(item.get("path"), str) and item["path"]:
            found.append(item["path"])
    return found


def _node_path(node: dict) -> str | None:
    path = (node.get("props") or {}).get("path")
    if isinstance(path, str) and path:
        return "game." + script_key(path)
    return None


def _needs_read(node: dict | None) -> bool:
    if node is None:
        return True
    return node.get("status") in {"unverified", "stale"}


def _about_target(place: Place, found: _Record, goal_id: str) -> str | None:
    node, _path = _target(place, goal_id, found)
    if node is not None:
        return node["id"]
    for item in place.nodes():
        if item.get("type") == "place":
            return item["id"]
    return None


def _is_verify(intent: dict) -> bool:
    props = intent.get("props") or {}
    return props.get("worker") == "playtest" and props.get("action") in _VERIFY_ACTIONS


def _kind(evidence: dict, studio: dict) -> str:
    console = studio.get("console") if isinstance(studio.get("console"), dict) else {}
    if console.get("reset") is True:
        return "reset"
    verdict = evidence.get("verdict")
    if verdict in {"pass", "fail"}:
        return verdict
    return "inconclusive"


def _signature(studio: dict) -> tuple:
    failed = []
    for check in _failed_checks(studio):
        failed.append(
            (
                str(check.get("id") or ""),
                str(check.get("expect") or ""),
                " ".join(str(check.get("detail") or "").split()),
            )
        )
    failures = studio.get("failures") if isinstance(studio.get("failures"), list) else []
    texts = tuple(" ".join(str(item).split()) for item in failures)
    return (tuple(sorted(failed)), texts)


def _failed_checks(studio: dict) -> list[dict]:
    checks = studio.get("checks")
    if not isinstance(checks, list):
        return []
    return [item for item in checks if isinstance(item, dict) and item.get("passed") is False]


def _failure_label(found: _Record) -> tuple[str, str]:
    failed = _failed_checks(found.studio)
    if failed:
        check = failed[0]
        check_id = str(check.get("id") or "check")
        detail = " ".join(str(check.get("detail") or check.get("expect") or "").split())
        quote = f"{check_id} failed: {detail}" if detail else f"{check_id} failed"
        return check_id, quote
    failures = found.studio.get("failures") if isinstance(found.studio.get("failures"), list) else []
    if failures:
        return "failure", " ".join(str(failures[0]).split())
    summary = " ".join(str(found.evidence.get("summary") or "Playtest checks failed.").split())
    return "failure", summary


def _primary_check_id(found: _Record) -> str:
    check_id, _quote = _failure_label(found)
    if check_id != "failure":
        return check_id
    ids = _check_ids(found.studio)
    return ids or "output"


def _check_ids(studio: dict) -> str:
    checks = studio.get("checks")
    if not isinstance(checks, list):
        return ""
    ids = [str(item.get("id")) for item in checks if isinstance(item, dict) and item.get("id")]
    return ", ".join(ids[:3])


def _done_when(intent: dict, fallback: str) -> str:
    done = (intent.get("props") or {}).get("done_when")
    if isinstance(done, str) and done.strip():
        return done.strip()
    return fallback


def _must_not(intent: dict, fallback: list[str]) -> list[str]:
    raw = (intent.get("props") or {}).get("must_not")
    if isinstance(raw, list) and raw and all(isinstance(item, str) and item for item in raw):
        return list(raw)
    return list(fallback)


def _fresh(place: Place, stem: str) -> str:
    used = {node.get("id") for node in place.nodes()}
    candidate = stem
    number = 2
    while candidate in used:
        candidate = f"{stem}-{number}"
        number += 1
    return candidate


def _next_order(place: Place) -> int:
    orders = [
        order
        for intent in place.intents()
        if isinstance(order := (intent.get("props") or {}).get("order"), int)
    ]
    return max(orders, default=0) + 1


def _rank(intent: dict) -> tuple:
    order = (intent.get("props") or {}).get("order")
    if not isinstance(order, int):
        order = 10**9
    return (order, str(intent.get("id")))


def _next_line(intent: dict) -> str:
    props = intent.get("props") or {}
    after = props.get("after")
    if after:
        return f"waiting {intent['id']} after {after}"
    return f"next {intent['id']} {props.get('worker')} {props.get('action')} ({intent.get('status')})"


def _clip(text: str, limit: int = 200) -> str:
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1].rstrip() + "…"
