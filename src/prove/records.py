"""Build prove.evidence/1 and prove.worker-result/1 objects."""

from __future__ import annotations

from prove.graph import utc_now


def evidence_id_for(intent_id: str) -> str:
    if intent_id.startswith("intent:"):
        return "evidence:" + intent_id[len("intent:") :]
    return "evidence:" + intent_id


def envelope(
    *,
    intent_id: str,
    place_id: str,
    worker: str,
    verdict: str,
    summary: str,
    limits: str,
    observations: list[dict] | None = None,
    artifacts: list[dict] | None = None,
    studio: dict | None = None,
    captured_at: str | None = None,
) -> dict:
    body = {
        "schema": "prove.evidence/1",
        "id": evidence_id_for(intent_id),
        "intent_id": intent_id,
        "place_id": place_id,
        "worker": worker,
        "captured_at": captured_at or utc_now(),
        "verdict": verdict,
        "summary": summary[:300],
        "observations": list(observations or []),
        "artifacts": list(artifacts or []),
        "limits": limits,
    }
    if studio is not None:
        body["studio"] = studio
    return body


def evidence_node(evidence: dict, stored_path: str) -> dict:
    return {
        "id": evidence["id"],
        "type": "evidence",
        "name": evidence["summary"][:80],
        "status": evidence["verdict"],
        "props": {"path": stored_path, "summary": evidence["summary"]},
    }


def worker_result(
    *,
    intent_id: str,
    evidence: dict,
    nodes: list[dict] | None = None,
    edges: list[dict] | None = None,
    statuses: list[dict] | None = None,
    follow_ups: list[dict] | None = None,
) -> dict:
    return {
        "schema": "prove.worker-result/1",
        "intent_id": intent_id,
        "evidence": evidence,
        "graph_patch": {
            "upsert_nodes": list(nodes or []),
            "upsert_edges": list(edges or []),
            "set_status": list(statuses or []),
        },
        "follow_ups": list(follow_ups or []),
    }
