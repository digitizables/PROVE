"""Create a place file and record goals, answers, and script bodies.

These commands edit the place graph. They do not call Studio.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from prove.graph import Place, PlaceError, script_key, slug, utc_now
from prove.planner import play_summary, playtest_inputs, queue_read

SAMPLE = (
    "Copy this sample to graph/places/<id>.local.json and plan that file. "
    "The checked-in example stays unchanged."
)
_PLACE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


def init_place(path: str | Path, place_id: str, title: str, display_name: str) -> Place:
    """Write a new place file with one place node and no goals."""
    dest = Path(path)
    if dest.name == "example.place.json":
        raise PlaceError(SAMPLE)
    if dest.exists():
        raise PlaceError(f"{dest} already exists")
    if not _PLACE_ID.fullmatch(place_id):
        raise PlaceError("Place id must be letters, digits, dots, underscores, or hyphens")
    if not title.strip() or not display_name.strip():
        raise PlaceError("Title and display name are required")
    dest.parent.mkdir(parents=True, exist_ok=True)
    place = Place(
        dest,
        {
            "schema": "prove.place/1",
            "id": place_id,
            "title": title.strip(),
            "identity": {
                "place_id": None,
                "universe_id": None,
                "file_name": None,
                "display_name": display_name.strip(),
            },
            "updated_at": "1970-01-01T00:00:00Z",
            "nodes": [
                {
                    "id": f"place:{slug(place_id)}",
                    "type": "place",
                    "name": title.strip(),
                    "status": "active",
                    "props": {},
                }
            ],
            "edges": [],
        },
    )
    place.save()
    return place


def add_goal(
    place: Place,
    *,
    statement: str,
    contains: list[str],
    absent: list[str],
    script: str | None,
    class_name: str,
    seconds: float,
    name: str | None,
    probes: list[dict] | None = None,
    forbid_errors: bool | None = None,
) -> list[str]:
    """Add one open goal and one unverified claim. Plan turns the claim into intents."""
    _refuse_sample(place)
    text = statement.strip()
    if not text:
        raise PlaceError("Statement is empty")
    if not contains and not absent and not probes:
        raise PlaceError("A goal needs --contains, --absent, or --probe")
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or seconds <= 0:
        raise PlaceError("Seconds must be a positive number")
    check = _compose_check(
        {},
        contains=contains or None,
        absent=absent or None,
        probes=probes or None,
        seconds=seconds,
        forbid_errors=forbid_errors,
    )
    label = (name or text).strip()
    stem = slug(label)[:48]
    goal_id = _fresh(place, f"goal:{stem}")
    claim_id = _fresh(place, f"claim:{stem}")
    claim_props: dict = {"goal_id": goal_id, "statement": text, "check": check}
    lines = [f"goal {goal_id}", f"claim {claim_id}"]
    place.nodes().append(
        {
            "id": goal_id,
            "type": "goal",
            "name": label[:80],
            "status": "open",
            "props": {"statement": text},
        }
    )
    if script:
        if not class_name.strip():
            raise PlaceError("Class name is empty")
        node = _ensure_script(place, script, class_name.strip(), text[:120])
        claim_props["path"] = node["props"]["path"]
        _edge(place, f"edge:{claim_id}:about:{node['id']}", "about", claim_id, node["id"])
        lines.append(f"script {node['id']}")
    place.nodes().append(
        {
            "id": claim_id,
            "type": "claim",
            "name": label[:80],
            "status": "unverified",
            "props": claim_props,
        }
    )
    place._assert_graph()
    return lines


def fill_source(place: Place, intent_id: str, source: str) -> None:
    """Put the script body on the ready write intent. Run still performs the write."""
    _refuse_sample(place)
    if source == "":
        raise PlaceError("Source is empty")
    question = _open_question(place)
    if question is not None:
        raise PlaceError(f"Answer {question['id']} before filling a write")
    ready = place.next_intent()
    if ready is None or ready["id"] != intent_id:
        raise PlaceError(f"{intent_id} is not the ready intent")
    props = ready.get("props") or {}
    if props.get("worker") != "script" or props.get("action") != "write_source":
        raise PlaceError(f"{intent_id} is not a write_source intent")
    inputs = props.get("inputs")
    if not isinstance(inputs, dict):
        raise PlaceError(f"{intent_id} is missing inputs")
    inputs["source"] = source


def bind_claim(
    place: Place,
    claim_id: str,
    *,
    script: str | None = None,
    class_name: str = "Script",
    contains: list[str] | None = None,
    absent: list[str] | None = None,
    probes: list[dict] | None = None,
    seconds: float | None = None,
    forbid_errors: bool | None = None,
) -> list[str]:
    """Point a claim at a script, replace its check, or both. Does not call Studio.

    A proposed verify that checks the claim takes the new playtest inputs.
    A new script with no local source gets a read, and that verify waits on it.
    A finished verify is left as it is.
    """
    _refuse_sample(place)
    claim = place.node(claim_id)
    if claim is None or claim.get("type") != "claim":
        raise PlaceError(f"No claim named {claim_id}")
    if (
        script is None
        and not contains
        and not absent
        and not probes
        and seconds is None
        and forbid_errors is None
    ):
        raise PlaceError("Bind needs a script path or a check change")
    if script is not None:
        if not str(class_name or "").strip():
            raise PlaceError("Class name is empty")
        if "." not in script_key(script):
            raise PlaceError("Script path needs a service and a script name, like game.ServerScriptService.Hello")
    props = claim.get("props")
    if not isinstance(props, dict):
        props = {}
        claim["props"] = props
    lines: list[str] = []
    check_changed = False
    if contains or absent or probes or seconds is not None or forbid_errors is not None:
        props["check"] = _compose_check(
            props.get("check") if isinstance(props.get("check"), dict) else {},
            contains=contains or None,
            absent=absent or None,
            probes=probes or None,
            seconds=seconds,
            forbid_errors=forbid_errors,
        )
        check_changed = True
        lines.append(f"check {claim_id}")
    node = None
    path = None
    if script is not None:
        if not class_name.strip():
            raise PlaceError("Class name is empty")
        node = _ensure_script(place, script, class_name.strip(), str(props.get("statement") or claim.get("name") or "")[:120])
        path = node["props"]["path"]
        props["path"] = path
        _retarget_script(place, claim_id, node["id"])
        lines.append(f"script {node['id']}")
    verifies = _proposed_verifies(place, claim_id)
    if check_changed:
        inputs = playtest_inputs(props.get("check")) or {}
        summary = play_summary(claim_id, inputs)
        for intent in verifies:
            _apply_play_inputs(intent, inputs)
            intent["props"]["summary"] = summary
            if path is None:
                lines.append(f"updated {intent['id']}")
    if path is not None:
        goal_id = props.get("goal_id")
        read, created = queue_read(
            place,
            goal_id=goal_id if isinstance(goal_id, str) else "",
            claim_id=claim_id,
            path=path,
            node=node,
        )
        if created and read is not None:
            lines.append(f"added {read['id']} script read_source")
        if read is not None:
            for intent in verifies:
                intent["props"]["after"] = read["id"]
                lines.append(f"waiting {intent['id']} after {read['id']}")
    place._assert_graph()
    return lines


def answer_question(place: Place, question_id: str, text: str) -> None:
    """Record the person's answer on an open question."""
    _refuse_sample(place)
    if not text.strip():
        raise PlaceError("Answer text is empty")
    node = place.node(question_id)
    if node is None or node.get("type") != "question":
        raise PlaceError(f"No question named {question_id}")
    if node.get("status") != "open":
        raise PlaceError(f"{question_id} is {node.get('status')}")
    node["status"] = "answered"
    props = node.get("props")
    if not isinstance(props, dict):
        props = {}
        node["props"] = props
    props["answer"] = text.strip()
    props["answered_at"] = utc_now()
    _release_stop(place, question_id)


def _release_stop(place: Place, question_id: str) -> None:
    """The blocked intent was waiting on this answer. Reject it so plan can continue."""
    for intent in place.intents():
        if intent.get("status") != "blocked":
            continue
        props = intent.get("props") or {}
        linked = props.get("question_id")
        summary = str(props.get("summary") or "")
        if linked != question_id and question_id not in summary:
            continue
        intent["status"] = "rejected"
        if isinstance(props, dict):
            props["reason"] = "The person answered the question."


def _refuse_sample(place: Place) -> None:
    if place.path.name == "example.place.json":
        raise PlaceError(SAMPLE)


def _open_question(place: Place) -> dict | None:
    for node in place.nodes():
        if node.get("type") == "question" and node.get("status") == "open":
            return node
    return None


def _ensure_script(place: Place, path: str, class_name: str, responsibility: str) -> dict:
    key = script_key(path)
    if "." not in key:
        raise PlaceError("Script path needs a service and a script name, like game.ServerScriptService.Hello")
    existing = place.find_script(key)
    if existing is not None:
        props = existing.setdefault("props", {})
        props.setdefault("path", "game." + key)
        props.setdefault("class_name", class_name)
        return existing
    service_name, _leaf = key.split(".", 1)
    leaf = key.rsplit(".", 1)[-1]
    service = place.find_service(service_name)
    place_node = _place_node(place)
    if service is None:
        service = {
            "id": _fresh(place, f"service:{slug(service_name)}"),
            "type": "service",
            "name": service_name,
            "status": "unverified",
            "props": {"tree_path": service_name},
        }
        place.nodes().append(service)
        _edge(place, f"edge:{place_node['id']}:contains:{service['id']}", "contains", place_node["id"], service["id"])
    script = {
        "id": _fresh(place, f"script:{slug(key)}"),
        "type": "script",
        "name": leaf,
        "status": "unverified",
        "props": {
            "path": "game." + key,
            "class_name": class_name,
            "responsibility": responsibility,
        },
    }
    place.nodes().append(script)
    _edge(place, f"edge:{service['id']}:contains:{script['id']}", "contains", service["id"], script["id"])
    return script


def _place_node(place: Place) -> dict:
    found = [node for node in place.nodes() if node.get("type") == "place"]
    if len(found) != 1:
        raise PlaceError("The place file needs one place node")
    return found[0]


def _edge(place: Place, edge_id: str, edge_type: str, source: str, target: str) -> None:
    for edge in place.data["edges"]:
        if edge.get("id") == edge_id:
            return
        if edge.get("type") == edge_type and edge.get("from") == source and edge.get("to") == target:
            return
    place.data["edges"].append({"id": edge_id, "type": edge_type, "from": source, "to": target})


def _compose_check(
    base: dict,
    *,
    contains: list[str] | None,
    absent: list[str] | None,
    probes: list[dict] | None,
    seconds: float | None,
    forbid_errors: bool | None,
) -> dict:
    check = copy.deepcopy(base)
    if not isinstance(check.get("screenshot"), bool):
        check["screenshot"] = False
    if seconds is not None:
        check["seconds"] = _seconds(seconds)
    elif "seconds" not in check:
        check["seconds"] = 3
    else:
        check["seconds"] = _seconds(check["seconds"])
    if contains:
        check["expect_contains"] = _strings(contains, "contains")
        if not probes:
            check.pop("probes", None)
    if absent:
        check["expect_absent"] = _strings(absent, "absent")
    if probes:
        check["probes"] = _clean_probes(probes)
        if not contains:
            check.pop("expect_contains", None)
        if not absent:
            check.pop("expect_absent", None)
    if forbid_errors is not None:
        check["forbid_errors"] = bool(forbid_errors)
    elif _probe_only(check):
        check["forbid_errors"] = False
    if playtest_inputs(check) is None:
        raise PlaceError("A check needs --contains, --absent, or --probe")
    return check


def _probe_only(check: dict) -> bool:
    probes = check.get("probes")
    return bool(probes) and not check.get("expect_contains") and not check.get("expect_absent")


def _clean_probes(items: list) -> list[dict]:
    if not isinstance(items, list) or not items:
        raise PlaceError("A probe list is empty")
    cleaned = []
    seen: set[str] = set()
    for index, item in enumerate(items, start=1):
        label = f"probes[{index}]"
        if not isinstance(item, dict):
            raise PlaceError(f"{label} must be an object")
        probe_id = item.get("id")
        expression = item.get("expression")
        datamodel = item.get("datamodel")
        if not isinstance(probe_id, str) or probe_id.strip() == "":
            raise PlaceError(f"{label}.id must be a non-empty string")
        if probe_id in seen:
            raise PlaceError(f"{label}.id duplicates {probe_id!r}")
        seen.add(probe_id)
        if not isinstance(expression, str) or expression.strip() == "" or "\n" in expression or "\r" in expression:
            raise PlaceError(f"{label}.expression must be one single-line Luau expression")
        if datamodel not in ("Server", "Client"):
            raise PlaceError(f"{label}.datamodel must be Server or Client")
        probe = {"id": probe_id, "expression": expression, "datamodel": datamodel}
        if "equals" in item:
            try:
                json.dumps(item["equals"])
            except TypeError as exc:
                raise PlaceError(f"{label}.equals must be JSON") from exc
            probe["equals"] = item["equals"]
        cleaned.append(probe)
    return cleaned


def _seconds(value: object) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise PlaceError("Seconds must be a positive number")
    number = float(value)
    return int(number) if number.is_integer() else number


def _proposed_verifies(place: Place, claim_id: str) -> list[dict]:
    found = []
    for intent in place.intents():
        if intent.get("status") != "proposed":
            continue
        props = intent.get("props") or {}
        if props.get("worker") != "playtest" or props.get("action") not in {"verify_output", "change_and_verify"}:
            continue
        if claim_id in place.claims_checked_by(intent["id"]):
            found.append(intent)
    return found


def _apply_play_inputs(intent: dict, inputs: dict) -> None:
    current = (intent.get("props") or {}).get("inputs")
    if not isinstance(current, dict):
        current = {}
        intent["props"]["inputs"] = current
    for key in ("seconds", "screenshot", "expect_contains", "expect_absent", "forbid_errors", "probes"):
        if key in inputs:
            current[key] = copy.deepcopy(inputs[key])
        else:
            current.pop(key, None)


def _retarget_script(place: Place, claim_id: str, script_id: str) -> None:
    kept = []
    for edge in place.data["edges"]:
        if edge.get("type") == "about" and edge.get("from") == claim_id:
            target = place.node(str(edge.get("to")))
            if target is not None and target.get("type") == "script":
                continue
        kept.append(edge)
    place.data["edges"] = kept
    _edge(place, f"edge:{claim_id}:about:{script_id}", "about", claim_id, script_id)


def _strings(values: list[str], label: str) -> list[str]:
    cleaned = []
    for item in values:
        if not isinstance(item, str) or item.strip() == "":
            raise PlaceError(f"{label} needs text")
        cleaned.append(item)
    return cleaned


def _fresh(place: Place, stem: str) -> str:
    used = {node.get("id") for node in place.nodes()}
    candidate = stem
    number = 2
    while candidate in used:
        candidate = f"{stem}-{number}"
        number += 1
    return candidate
