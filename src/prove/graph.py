"""Load a place file, choose the next intent, and apply a graph patch."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "prove.place/1"


class PlaceError(Exception):
    """The place file or a patch broke a graph rule."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def script_key(path: str) -> str:
    """Script path with a leading ``game.`` removed, for comparison."""
    text = path.strip().strip(".")
    if text.startswith("game."):
        return text[5:]
    return text


def slug(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return cleaned or "node"


class Place:
    def __init__(self, path: Path, data: dict) -> None:
        self.path = path
        self.data = data

    @classmethod
    def load(cls, path: str | Path) -> Place:
        file = Path(path)
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise PlaceError(f"{file} is not JSON: {exc}") from exc
        if not isinstance(data, dict) or data.get("schema") != SCHEMA:
            raise PlaceError(f"{file} is not a {SCHEMA} place file")
        for key in ("id", "nodes", "edges", "identity"):
            if key not in data:
                raise PlaceError(f"{file} is missing {key}")
        return cls(file, data)

    def save(self) -> None:
        self.data["updated_at"] = utc_now()
        text = json.dumps(self.data, indent=2) + "\n"
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(self.path)

    def nodes(self) -> list[dict]:
        return self.data["nodes"]

    def node(self, node_id: str) -> dict | None:
        for item in self.nodes():
            if item.get("id") == node_id:
                return item
        return None

    def intents(self) -> list[dict]:
        return [item for item in self.nodes() if item.get("type") == "intent"]

    def active_intent(self) -> dict | None:
        active = [item for item in self.intents() if item.get("status") == "active"]
        if len(active) > 1:
            names = ", ".join(item["id"] for item in active)
            raise PlaceError(f"More than one intent is active: {names}")
        return active[0] if active else None

    def next_intent(self) -> dict | None:
        """The active intent, or the earliest proposed intent whose ``after`` is done."""
        active = self.active_intent()
        if active is not None:
            return active
        done = {item["id"] for item in self.intents() if item.get("status") == "done"}
        ready = []
        for intent in self.intents():
            if intent.get("status") != "proposed":
                continue
            after = (intent.get("props") or {}).get("after")
            if after and after not in done:
                continue
            ready.append(intent)
        if not ready:
            return None
        ready.sort(key=_intent_sort)
        return ready[0]

    def activate(self, intent_id: str) -> dict:
        current = self.active_intent()
        if current is not None and current["id"] != intent_id:
            raise PlaceError(f"{current['id']} is already active")
        intent = self.node(intent_id)
        if intent is None or intent.get("type") != "intent":
            raise PlaceError(f"No intent named {intent_id}")
        if intent["status"] == "active":
            return intent
        if intent["status"] != "proposed":
            raise PlaceError(f"{intent_id} is {intent['status']}")
        after = (intent.get("props") or {}).get("after")
        if after:
            previous = self.node(after)
            if previous is None or previous.get("status") != "done":
                raise PlaceError(f"{intent_id} waits on {after}")
        intent["status"] = "active"
        return intent

    def claims_checked_by(self, intent_id: str) -> list[str]:
        return [
            edge["to"]
            for edge in self.data["edges"]
            if edge.get("type") == "checks" and edge.get("from") == intent_id
        ]

    def apply_patch(self, patch: dict) -> None:
        for node in patch.get("upsert_nodes") or []:
            _require_fields(node, ("id", "type", "name", "status", "props"), "node")
            self._replace("nodes", node)
        for edge in patch.get("upsert_edges") or []:
            _require_fields(edge, ("id", "type", "from", "to"), "edge")
            self._replace("edges", edge)
        for change in patch.get("set_status") or []:
            target = self.node(str(change.get("id")))
            if target is None:
                raise PlaceError(f"set_status names missing node {change.get('id')}")
            target["status"] = change["status"]
        self._assert_graph()

    def add_follow_ups(self, follow_ups: list[dict]) -> None:
        for intent in follow_ups:
            if self.node(intent["id"]) is not None:
                continue
            _require_fields(intent, ("id", "type", "name", "status", "props"), "follow-up")
            if intent["type"] != "intent" or intent["status"] != "proposed":
                raise PlaceError(f"Follow-up {intent.get('id')} must be a proposed intent")
            self.nodes().append(intent)
            goal_id = (intent.get("props") or {}).get("goal_id")
            if isinstance(goal_id, str) and self.node(goal_id) is not None:
                edge_id = f"edge:{intent['id']}:goal"
                if not any(edge.get("id") == edge_id for edge in self.data["edges"]):
                    self.data["edges"].append(
                        {
                            "id": edge_id,
                            "type": "spawned_from",
                            "from": intent["id"],
                            "to": goal_id,
                        }
                    )
        self._assert_graph()

    def close_goals(self) -> None:
        """Mark an open goal done when its intents are finished and their claims are supported."""
        for goal in self.nodes():
            if goal.get("type") != "goal" or goal.get("status") != "open":
                continue
            intent_ids = [
                edge["from"]
                for edge in self.data["edges"]
                if edge.get("type") == "spawned_from" and edge.get("to") == goal["id"]
            ]
            intents = [item for item in (self.node(intent_id) for intent_id in intent_ids) if item is not None]
            if not intents:
                continue
            if any(item.get("status") in {"proposed", "active", "blocked"} for item in intents):
                continue
            claims: list[str] = []
            for intent in intents:
                claims.extend(self.claims_checked_by(intent["id"]))
            if not claims:
                continue
            if all((found := self.node(claim_id)) is not None and found.get("status") == "supported" for claim_id in claims):
                goal["status"] = "done"

    def find_script(self, path: str) -> dict | None:
        key = script_key(path)
        for item in self.nodes():
            if item.get("type") != "script":
                continue
            if script_key(str((item.get("props") or {}).get("path") or "")) == key:
                return item
        return None

    def find_service(self, name: str) -> dict | None:
        folded = name.casefold()
        for item in self.nodes():
            if item.get("type") != "service":
                continue
            tree = str((item.get("props") or {}).get("tree_path") or "")
            if item.get("name", "").casefold() == folded or tree.casefold() == folded:
                return item
        return None

    def find_instance(self, tree_path: str) -> dict | None:
        for item in self.nodes():
            if item.get("type") != "instance":
                continue
            if str((item.get("props") or {}).get("tree_path") or "") == tree_path:
                return item
        return None

    def _replace(self, key: str, item: dict) -> None:
        rows = self.data[key]
        for index, existing in enumerate(rows):
            if existing.get("id") == item["id"]:
                rows[index] = item
                return
        rows.append(item)

    def _assert_graph(self) -> None:
        ids = [item["id"] for item in self.nodes()]
        if len(ids) != len(set(ids)):
            raise PlaceError("Place file has duplicate node ids")
        known = set(ids)
        active = [item["id"] for item in self.intents() if item.get("status") == "active"]
        if len(active) > 1:
            raise PlaceError("More than one intent is active: " + ", ".join(active))
        for edge in self.data["edges"]:
            if edge.get("from") not in known or edge.get("to") not in known:
                raise PlaceError(f"Edge {edge.get('id')} points outside the graph")


def _intent_sort(intent: dict) -> tuple:
    order = (intent.get("props") or {}).get("order")
    if not isinstance(order, int):
        order = 10**9
    return (order, str(intent.get("id")))


def _require_fields(item: dict, fields: tuple[str, ...], label: str) -> None:
    missing = [field for field in fields if field not in item]
    if missing:
        raise PlaceError(f"{label} is missing {', '.join(missing)}")
