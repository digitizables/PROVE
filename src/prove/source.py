"""Find the newest script body stored in a local evidence file.

The place graph keeps the hash. The body lives in the worker-result file.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from prove.graph import Place, script_key
from prove.session import locate_root


@dataclass(frozen=True)
class SourceRecord:
    text: str
    evidence_path: str | None
    sha256: str


def latest_source(place: Place, path: str) -> SourceRecord | None:
    """The newest recorded body for ``path``, or None when no local record has one."""
    key = script_key(path)
    best_rank: tuple | None = None
    best: SourceRecord | None = None

    def consider(rank: tuple, text: str, evidence_path: str | None, sha: str | None) -> None:
        nonlocal best_rank, best
        if text == "":
            return
        if best_rank is not None and rank <= best_rank:
            return
        digest = sha or hashlib.sha256(text.encode("utf-8")).hexdigest()
        best_rank = rank
        best = SourceRecord(text, evidence_path, digest)

    for node in place.nodes():
        if node.get("type") != "evidence":
            continue
        stored = (node.get("props") or {}).get("path")
        if not isinstance(stored, str) or stored == "":
            continue
        evidence = _load(place, stored)
        if evidence is None:
            continue
        observations = evidence.get("observations")
        script = _observation(observations, "script_path")
        text = _observation(observations, "source")
        if script is None or text is None or script_key(script) != key:
            continue
        intent = place.node(str(evidence.get("intent_id") or ""))
        consider(_rank(intent, node.get("id")), text, stored, _observation(observations, "source_sha256"))

    for intent in place.intents():
        if intent.get("status") != "done":
            continue
        props = intent.get("props") or {}
        inputs = props.get("inputs") or {}
        if not isinstance(inputs, dict):
            continue
        rank = _rank(intent, intent.get("id"))
        if props.get("action") == "write_source":
            raw = inputs.get("path")
            text = inputs.get("source")
            if isinstance(raw, str) and isinstance(text, str) and script_key(raw) == key:
                consider(rank, text, None, None)
        if props.get("action") == "change_and_verify":
            for item in inputs.get("scripts") or []:
                if not isinstance(item, dict):
                    continue
                raw = item.get("path")
                text = item.get("source")
                if isinstance(raw, str) and isinstance(text, str) and script_key(raw) == key:
                    consider(rank, text, None, None)
    return best


def _observation(observations: object, kind: str) -> str | None:
    if not isinstance(observations, list):
        return None
    for item in observations:
        if isinstance(item, dict) and item.get("kind") == kind and isinstance(item.get("text"), str):
            return item["text"]
    return None


def _rank(intent: dict | None, fallback: object) -> tuple:
    if not intent:
        return (0, str(fallback))
    order = (intent.get("props") or {}).get("order")
    if not isinstance(order, int):
        order = 0
    return (order, str(intent.get("id")))


def _load(place: Place, stored: str) -> dict | None:
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
