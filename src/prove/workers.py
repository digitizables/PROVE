"""Workers the runtime knows how to execute.

Allowed adapter methods for every worker, including ones this runtime does
not run, are in workers/catalog.md.
"""

from __future__ import annotations

import copy
import hashlib
from typing import Any

from prove.graph import Place, script_key, slug
from prove.records import envelope, evidence_node, worker_result
from prove.verdict import verdict_from_studio

_SCRIPT_CLASSES = {"Script", "LocalScript", "ModuleScript"}
_SOURCE_LIMITS = (
    "The place graph stores the hash. This local file stores the source text and stays uncommitted."
)


class NeedPerson(Exception):
    """The intent cannot run until a person changes it or answers."""


def read_source(place: Place, agent: Any, intent: dict, stored_path: str) -> dict:
    path = _require(intent, "path")
    document = agent.scripts.read(path)
    source = str(document.source)
    return _script_observation(
        place,
        intent,
        stored_path,
        path,
        source,
        summary=f"Read {path}.",
        limits=_SOURCE_LIMITS,
    )


def write_source(place: Place, agent: Any, intent: dict, stored_path: str) -> dict:
    path = _require(intent, "path")
    source = _require(intent, "source")
    class_name = (intent["props"].get("inputs") or {}).get("class_name", "auto")
    normalized = _normalize(source)
    agent.scripts.write(path, normalized, class_name=class_name)
    result = _script_observation(
        place,
        intent,
        stored_path,
        path,
        normalized,
        summary=f"Wrote {path}.",
        limits=_SOURCE_LIMITS + " A write is not a playtest. Behavior stays unverified until a later intent.",
    )
    _drop_written_source(result, intent)
    return result


def verify_output(place: Place, agent: Any, intent: dict, stored_path: str) -> dict:
    from roblox_studio_adapter.evidence import evidence_record

    inputs = intent["props"].get("inputs") or {}
    report = agent.playtest.run(
        seconds=float(inputs.get("seconds", 3)),
        screenshot=bool(inputs.get("screenshot", False)),
        expect_contains=inputs.get("expect_contains"),
        expect_absent=inputs.get("expect_absent"),
        forbid_errors=bool(inputs.get("forbid_errors", True)),
        probes=inputs.get("probes"),
    )
    studio = evidence_record(report, studio_id=getattr(agent.session, "studio_id", None), intent_id=intent["id"])
    return _from_studio(place, intent, stored_path, studio, worker="playtest")


def change_and_verify(place: Place, agent: Any, intent: dict, stored_path: str) -> dict:
    inputs = intent["props"].get("inputs") or {}
    raw = agent.loop.change_and_verify(
        scripts=inputs.get("scripts"),
        instances=inputs.get("instances"),
        seconds=float(inputs.get("seconds", 3)),
        expect_contains=inputs.get("expect_contains"),
        expect_absent=inputs.get("expect_absent"),
        forbid_errors=bool(inputs.get("forbid_errors", True)),
        screenshot=bool(inputs.get("screenshot", False)),
        intent_id=intent["id"],
        probes=inputs.get("probes"),
    )
    extra: list[dict] = []
    for written in raw.get("scripts") or []:
        match = _matching_script(inputs.get("scripts") or [], written.path)
        if match is None:
            continue
        extra.append(
            _script_node(
                place,
                match["path"],
                sha256_text(_normalize(match["source"])),
                class_name=match.get("class_name"),
            )
        )
    for tree_path in raw.get("instances") or []:
        class_name = _class_for_instance(inputs.get("instances") or [], tree_path)
        extra.append(_instance_node(place, tree_path, class_name))
    result = _from_studio(place, intent, stored_path, raw["evidence"], worker="playtest", extra_nodes=extra)
    for item in inputs.get("scripts") or []:
        if isinstance(item, dict) and isinstance(item.get("path"), str) and isinstance(item.get("source"), str):
            result["evidence"]["observations"].extend(source_observations(item["path"], _normalize(item["source"])))
    _drop_written_source(result, intent)
    return result


def overview(place: Place, agent: Any, intent: dict, stored_path: str) -> dict:
    report = agent.loop.explore()
    nodes: list[dict] = []
    services = report.get("services") or {}
    for name, lines in services.items():
        nodes.append(_service_node(place, str(name)))
        if not isinstance(lines, list):
            continue
        for line in lines:
            parsed = _script_line(str(line))
            if parsed is None:
                continue
            class_name, tree_path = parsed
            nodes.append(_script_node(place, tree_path, None, class_name=class_name))
    truncated = report.get("truncated") or []
    limits = "Overview records names, not script bodies."
    if truncated:
        limits += " Truncated: " + ", ".join(str(item) for item in truncated) + "."
    evidence = envelope(
        intent_id=intent["id"],
        place_id=str(place.data["id"]),
        worker="explore",
        verdict="inconclusive",
        summary=f"Explored {len(services)} services.",
        limits=limits,
        observations=[{"kind": "service", "text": name} for name in services],
    )
    patch_nodes, edges, statuses = _settle(place, intent, evidence, stored_path)
    return worker_result(
        intent_id=intent["id"],
        evidence=evidence,
        nodes=_dedupe(patch_nodes + nodes),
        edges=edges,
        statuses=statuses,
    )


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def source_observations(path: str, source: str) -> list[dict]:
    """Local evidence rows for one script body. The place graph stores the hash only."""
    return [
        {"kind": "script_path", "text": "game." + script_key(path)},
        {"kind": "source_sha256", "text": sha256_text(source)},
        {"kind": "source", "text": source},
    ]


def _script_observation(
    place: Place,
    intent: dict,
    stored_path: str,
    path: str,
    source: str,
    *,
    summary: str,
    limits: str,
) -> dict:
    digest = sha256_text(source)
    evidence = envelope(
        intent_id=intent["id"],
        place_id=str(place.data["id"]),
        worker="script",
        verdict="inconclusive",
        summary=summary,
        limits=limits,
        observations=source_observations(path, source),
    )
    nodes, edges, statuses = _settle(place, intent, evidence, stored_path)
    nodes.append(_script_node(place, path, digest))
    return worker_result(intent_id=intent["id"], evidence=evidence, nodes=_dedupe(nodes), edges=edges, statuses=statuses)


def _from_studio(
    place: Place,
    intent: dict,
    stored_path: str,
    studio: dict,
    *,
    worker: str,
    extra_nodes: list[dict] | None = None,
) -> dict:
    verdict = verdict_from_studio(studio)
    evidence = envelope(
        intent_id=intent["id"],
        place_id=str(place.data["id"]),
        worker=worker,
        verdict=verdict,
        summary=_play_summary(studio, verdict),
        limits=_play_limits(studio),
        observations=_play_observations(studio),
        artifacts=_artifacts(studio),
        studio=studio,
    )
    nodes, edges, statuses = _settle(place, intent, evidence, stored_path)
    nodes.extend(extra_nodes or [])
    return worker_result(intent_id=intent["id"], evidence=evidence, nodes=_dedupe(nodes), edges=edges, statuses=statuses)


def _settle(place: Place, intent: dict, evidence: dict, stored_path: str) -> tuple[list[dict], list[dict], list[dict]]:
    nodes = [evidence_node(evidence, stored_path)]
    edges: list[dict] = []
    statuses = [{"id": intent["id"], "status": "blocked" if evidence["verdict"] == "blocked" else "done"}]
    relation = {"pass": "supports", "fail": "contradicts"}.get(evidence["verdict"])
    claim_status = {"pass": "supported", "fail": "contradicted"}.get(evidence["verdict"])
    if relation and claim_status:
        for claim_id in place.claims_checked_by(intent["id"]):
            statuses.append({"id": claim_id, "status": claim_status})
            edges.append(
                {
                    "id": f"edge:{evidence['id']}:{relation}:{claim_id}",
                    "type": relation,
                    "from": evidence["id"],
                    "to": claim_id,
                }
            )
    return nodes, edges, statuses


def missing_input(intent: dict) -> str | None:
    """The first required input that is empty, or None when the intent can start."""
    props = intent.get("props") or {}
    inputs = props.get("inputs") or {}
    if not isinstance(inputs, dict):
        return "inputs"
    required: tuple[str, ...] = ()
    if props.get("worker") == "script" and props.get("action") == "read_source":
        required = ("path",)
    elif props.get("worker") == "script" and props.get("action") == "write_source":
        required = ("path", "source")
    for key in required:
        value = inputs.get(key)
        if not isinstance(value, str) or value == "":
            return key
    return None


def require_ready(intent: dict) -> None:
    """Raise before Studio is contacted when a required input is empty."""
    missing = missing_input(intent)
    if missing:
        raise NeedPerson(f"{intent['id']} is missing inputs.{missing}")


def _require(intent: dict, key: str) -> str:
    value = (intent["props"].get("inputs") or {}).get(key)
    if not isinstance(value, str) or value == "":
        raise NeedPerson(f"{intent['id']} is missing inputs.{key}")
    return value


def _normalize(source: str) -> str:
    return source.replace("\r\n", "\n").replace("\r", "\n")


def _drop_written_source(result: dict, intent: dict) -> None:
    """Remove script bodies from the intent stored on the place graph.

    The worker-result file keeps the text. A later session reads it from there.
    """
    cleaned = copy.deepcopy(intent)
    inputs = dict((cleaned.get("props") or {}).get("inputs") or {})
    inputs.pop("source", None)
    scripts = []
    for item in inputs.get("scripts") or []:
        if isinstance(item, dict):
            item = dict(item)
            item.pop("source", None)
        scripts.append(item)
    if "scripts" in inputs:
        inputs["scripts"] = scripts
    cleaned["props"]["inputs"] = inputs
    result["graph_patch"]["upsert_nodes"].append(cleaned)


def _script_node(place: Place, path: str, digest: str | None, *, class_name: str | None = None) -> dict:
    existing = place.find_script(path)
    if existing is not None:
        props = dict(existing.get("props") or {})
        node = {
            "id": existing["id"],
            "type": "script",
            "name": existing.get("name") or script_key(path).rsplit(".", 1)[-1],
            "status": "observed",
            "props": props,
        }
    else:
        leaf = script_key(path).rsplit(".", 1)[-1]
        node = {
            "id": f"script:{slug(script_key(path))}",
            "type": "script",
            "name": leaf,
            "status": "observed",
            "props": {},
        }
    node["props"]["path"] = "game." + script_key(path)
    node["props"].pop("source", None)
    if digest:
        node["props"]["source_sha256"] = digest
    if class_name:
        node["props"]["class_name"] = class_name
    return node


def _service_node(place: Place, name: str) -> dict:
    existing = place.find_service(name)
    if existing is not None:
        props = dict(existing.get("props") or {})
        props.setdefault("tree_path", name)
        return {
            "id": existing["id"],
            "type": "service",
            "name": existing.get("name") or name,
            "status": "observed",
            "props": props,
        }
    return {
        "id": f"service:{slug(name)}",
        "type": "service",
        "name": name,
        "status": "observed",
        "props": {"tree_path": name},
    }


def _instance_node(place: Place, tree_path: str, class_name: str) -> dict:
    existing = place.find_instance(tree_path)
    leaf = tree_path.rsplit(".", 1)[-1]
    if existing is not None:
        props = dict(existing.get("props") or {})
        props["tree_path"] = tree_path
        if class_name:
            props["class_name"] = class_name
        return {
            "id": existing["id"],
            "type": "instance",
            "name": existing.get("name") or leaf,
            "status": "observed",
            "props": props,
        }
    return {
        "id": f"instance:{slug(tree_path)}",
        "type": "instance",
        "name": leaf,
        "status": "observed",
        "props": {"tree_path": tree_path, "class_name": class_name},
    }


def _script_line(line: str) -> tuple[str, str] | None:
    parts = line.split(" ", 1)
    if len(parts) != 2 or parts[0] not in _SCRIPT_CLASSES:
        return None
    return parts[0], parts[1]


def _matching_script(scripts: list[dict], written_path: str) -> dict | None:
    key = script_key(written_path)
    for item in scripts:
        if isinstance(item, dict) and script_key(str(item.get("path") or "")) == key:
            return item
    return None


def _class_for_instance(instances: list[dict], tree_path: str) -> str:
    leaf = tree_path.rsplit(".", 1)[-1]
    for item in instances:
        if isinstance(item, dict) and item.get("name") == leaf:
            return str(item.get("class_name") or "")
    return ""


def _play_summary(studio: dict, verdict: str) -> str:
    failures = [str(item) for item in studio.get("failures") or []]
    if verdict == "pass":
        return "Playtest checks passed."
    if failures:
        return failures[0]
    if verdict == "inconclusive":
        return "Playtest checks could not be isolated to this run."
    return "Playtest checks failed."


def _play_limits(studio: dict) -> str:
    parts = ["Solo playtest."]
    console = studio.get("console") or {}
    if console.get("reset"):
        parts.append("Console snapshot did not match the later log.")
    else:
        parts.append("Console delta was contiguous.")
    screenshots = (studio.get("artifacts") or {}).get("screenshots") or []
    if not screenshots:
        parts.append("No screenshot.")
    if not studio.get("probes"):
        parts.append("No Server or Client probe.")
    return " ".join(parts)


def _play_observations(studio: dict) -> list[dict]:
    observations = []
    for check in studio.get("checks") or []:
        if not check.get("passed"):
            observations.append({"kind": "check", "text": f"{check.get('id')} failed: {check.get('detail')}"})
    for probe in studio.get("probes") or []:
        if probe.get("ok"):
            observations.append({"kind": "probe", "text": f"{probe.get('id')}={probe.get('value')!r}"})
        else:
            observations.append({"kind": "probe", "text": f"{probe.get('id')} error: {probe.get('error')}"})
    return observations


def _artifacts(studio: dict) -> list[dict]:
    artifacts = []
    block = studio.get("artifacts") or {}
    for path in block.get("screenshots") or []:
        artifacts.append({"kind": "screenshot", "path": str(path)})
    video = block.get("video") or {}
    if isinstance(video, dict):
        for kind in ("video", "manifest", "frame_times"):
            path = (video.get("artifacts") or {}).get(kind) if "artifacts" in video else video.get(kind)
            if path:
                artifacts.append({"kind": kind, "path": str(path)})
    return artifacts


def _dedupe(nodes: list[dict]) -> list[dict]:
    by_id: dict[str, dict] = {}
    for node in nodes:
        by_id[node["id"]] = node
    return list(by_id.values())
