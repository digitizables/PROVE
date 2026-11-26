"""Create a place file and record goals, answers, and script bodies.

These commands edit the place graph. They do not call Studio.
"""

from __future__ import annotations

import re
from pathlib import Path

from prove.graph import Place, PlaceError, script_key, slug

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
) -> list[str]:
    """Add one open goal and one unverified claim. Plan turns the claim into intents."""
    _refuse_sample(place)
    text = statement.strip()
    if not text:
        raise PlaceError("Statement is empty")
    needles = _strings(contains, "contains")
    missing = _strings(absent, "absent")
    if not needles and not missing:
        raise PlaceError("A goal needs --contains or --absent")
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or seconds <= 0:
        raise PlaceError("Seconds must be a positive number")
    label = (name or text).strip()
    stem = slug(label)[:48]
    goal_id = _fresh(place, f"goal:{stem}")
    claim_id = _fresh(place, f"claim:{stem}")
    check: dict = {"screenshot": False, "seconds": int(seconds) if float(seconds).is_integer() else seconds}
    if needles:
        check["expect_contains"] = needles
    if missing:
        check["expect_absent"] = missing
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
