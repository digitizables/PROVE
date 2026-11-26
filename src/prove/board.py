"""A person-facing view of one place file.

The board reads the graph. It does not call Studio. Script bodies stay in the
local worker-result file and are left out of this view.
"""

from __future__ import annotations

import json
from pathlib import Path

from prove.brief import brief
from prove.graph import Place, PlaceError, _intent_sort
from prove.records import evidence_id_for
from prove.session import locate_root

_OBSERVATION_LIMIT = 500


def list_places(root: Path) -> list[dict]:
    """Place files under ``graph/places``, local files first."""
    folder = root / "graph" / "places"
    if not folder.is_dir():
        return []
    rows = []
    for path in folder.glob("*.json"):
        if not path.is_file():
            continue
        try:
            place = Place.load(path)
        except PlaceError:
            continue
        identity = place.data.get("identity") or {}
        rows.append(
            {
                "file": path.name,
                "id": place.data.get("id"),
                "title": place.data.get("title") or "",
                "display_name": identity.get("display_name") or "",
                "updated_at": place.data.get("updated_at") or "",
            }
        )
    rows.sort(key=lambda row: (not str(row["file"]).endswith(".local.json"), str(row["file"])))
    return rows


def resolve_place(root: Path, file_name: str) -> Path:
    """One file name inside ``graph/places``. Rejects paths that leave that folder."""
    name = str(file_name or "").strip()
    if not name or name != Path(name).name or not name.endswith(".json"):
        raise PlaceError("Place file must be a JSON name inside graph/places")
    folder = (root / "graph" / "places").resolve()
    path = (folder / name).resolve()
    if not path.is_relative_to(folder):
        raise PlaceError("Place file must stay inside graph/places")
    if not path.is_file():
        raise PlaceError(f"No place file named {name}")
    return path


def place_board(place: Place) -> dict:
    """Goals, claims, intents, and the one next action. No script source."""
    payload = dict(brief(place))
    payload.pop("source", None)
    identity = place.data.get("identity") or {}
    active = place.active_intent()
    nxt = place.next_intent()
    return {
        "file": place.path.name,
        "id": place.data.get("id"),
        "title": place.data.get("title") or "",
        "updated_at": place.data.get("updated_at") or "",
        "display_name": identity.get("display_name") or "",
        "place_id": identity.get("place_id"),
        "universe_id": identity.get("universe_id"),
        "active_intent": active["id"] if active else None,
        "next_intent": nxt["id"] if nxt else None,
        "brief": payload,
        "goals": [_goal(node) for node in place.nodes() if node.get("type") == "goal"],
        "claims": [_claim(place, node) for node in place.nodes() if node.get("type") == "claim"],
        "intents": [_intent(place, intent) for intent in sorted(place.intents(), key=_intent_sort)],
    }


def evidence_view(place: Place, intent_id: str) -> dict:
    """Summary, limits, checks, and observations for one intent.

    Observations of kind ``source`` are omitted. Those rows are the script body.
    """
    node = place.node(evidence_id_for(intent_id))
    props = (node.get("props") or {}) if node else {}
    stored = props.get("path") if isinstance(props.get("path"), str) else ""
    evidence = _load_evidence(place, stored) if stored else None
    if evidence is None:
        return {
            "intent_id": intent_id,
            "missing": True,
            "verdict": (node or {}).get("status") or "",
            "summary": str(props.get("summary") or ""),
            "limits": "",
            "captured_at": "",
            "observations": [],
            "checks": [],
        }
    studio = evidence.get("studio") if isinstance(evidence.get("studio"), dict) else {}
    checks = []
    for item in studio.get("checks") or []:
        if not isinstance(item, dict):
            continue
        checks.append(
            {
                "id": str(item.get("id") or ""),
                "passed": item.get("passed"),
                "detail": _clip(item.get("detail")),
            }
        )
    observations = []
    for item in evidence.get("observations") or []:
        if not isinstance(item, dict) or item.get("kind") == "source":
            continue
        observations.append({"kind": str(item.get("kind") or ""), "text": _clip(item.get("text"))})
    return {
        "intent_id": intent_id,
        "missing": False,
        "verdict": str(evidence.get("verdict") or (node or {}).get("status") or ""),
        "summary": str(evidence.get("summary") or props.get("summary") or ""),
        "limits": str(evidence.get("limits") or ""),
        "captured_at": str(evidence.get("captured_at") or ""),
        "observations": observations,
        "checks": checks,
    }


def _goal(node: dict) -> dict:
    props = node.get("props") or {}
    return {
        "id": node.get("id"),
        "name": node.get("name") or "",
        "status": node.get("status") or "",
        "statement": str(props.get("statement") or ""),
    }


def _claim(place: Place, node: dict) -> dict:
    props = node.get("props") or {}
    check = props.get("check") if isinstance(props.get("check"), dict) else None
    if not _has_check(check):
        check = _check_from_intent(place, str(node.get("id") or ""))
    return {
        "id": node.get("id"),
        "name": node.get("name") or "",
        "status": node.get("status") or "",
        "statement": str(props.get("statement") or ""),
        "goal_id": str(props.get("goal_id") or ""),
        "path": str(props.get("path") or ""),
        "check": _check_label(check),
        "check_detail": _public_check(check),
    }


def _intent(place: Place, intent: dict) -> dict:
    props = intent.get("props") or {}
    evidence = place.node(evidence_id_for(intent["id"]))
    evidence_props = (evidence.get("props") or {}) if evidence else {}
    return {
        "id": intent.get("id"),
        "name": intent.get("name") or "",
        "status": intent.get("status") or "",
        "worker": str(props.get("worker") or ""),
        "action": str(props.get("action") or ""),
        "summary": str(props.get("summary") or ""),
        "order": props.get("order") if isinstance(props.get("order"), int) else None,
        "after": props.get("after"),
        "verdict": str(evidence.get("status") or "") if evidence else "",
        "evidence_summary": str(evidence_props.get("summary") or ""),
    }


def _has_check(check: dict | None) -> bool:
    if not check:
        return False
    return bool(check.get("expect_contains") or check.get("expect_absent") or check.get("probes"))


def _check_from_intent(place: Place, claim_id: str) -> dict | None:
    """Older samples store the playtest needles on the verify intent, not the claim."""
    found: dict | None = None
    for edge in place.data.get("edges") or []:
        if edge.get("type") != "checks" or edge.get("to") != claim_id:
            continue
        intent = place.node(str(edge.get("from") or ""))
        if intent is None or intent.get("status") == "rejected":
            continue
        inputs = (intent.get("props") or {}).get("inputs")
        if isinstance(inputs, dict) and _has_check(inputs):
            found = inputs
    return found


def _check_label(check: dict | None) -> str:
    if not check:
        return ""
    parts: list[str] = []
    contains = check.get("expect_contains") or []
    absent = check.get("expect_absent") or []
    if isinstance(contains, list) and contains:
        parts.append("contains " + ", ".join(str(item) for item in contains))
    if isinstance(absent, list) and absent:
        parts.append("absent " + ", ".join(str(item) for item in absent))
    for probe in check.get("probes") or []:
        if not isinstance(probe, dict):
            continue
        label = str(probe.get("id") or "probe")
        datamodel = probe.get("datamodel")
        if datamodel:
            label = f"{label} {datamodel}"
        parts.append(f"probe {label}")
    seconds = check.get("seconds")
    if isinstance(seconds, (int, float)) and not isinstance(seconds, bool):
        parts.append(f"{int(seconds) if float(seconds).is_integer() else seconds}s")
    return " · ".join(parts)


def _public_check(check: dict | None) -> dict | None:
    if not check:
        return None
    public: dict = {}
    for key in ("seconds", "screenshot", "forbid_errors", "expect_contains", "expect_absent"):
        if key in check:
            public[key] = check[key]
    probes = []
    for probe in check.get("probes") or []:
        if not isinstance(probe, dict):
            continue
        item = {key: probe[key] for key in ("id", "expression", "datamodel") if key in probe}
        if "equals" in probe:
            item["equals"] = probe["equals"]
        probes.append(item)
    if probes:
        public["probes"] = probes
    return public


def _load_evidence(place: Place, stored: str) -> dict | None:
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
    sibling = place.path.parent / stored
    if sibling.is_file():
        return sibling
    return raw


def _clip(value: object) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= _OBSERVATION_LIMIT:
        return text
    return text[: _OBSERVATION_LIMIT - 1].rstrip() + "…"
