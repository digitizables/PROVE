"""Planner tests. They use saved evidence files and do not open Studio."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / "roblox-studio-adapter" / "src"))
sys.path.insert(0, str(ROOT / "src"))

from prove.cli import main  # noqa: E402
from prove.graph import Place  # noqa: E402
from prove.planner import plan  # noqa: E402
from prove.records import evidence_id_for  # noqa: E402
from prove.workers import NeedPerson  # noqa: E402
from prove.session import run_intent  # noqa: E402

EXAMPLE = ROOT / "graph" / "places" / "example.place.json"
HELLO = "game.ServerScriptService.HelloAgent"


class PlanCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def place(self, name: str = "game.local.json") -> Place:
        dest = self.root / name
        shutil.copy(EXAMPLE, dest)
        return Place.load(dest)

    def evidence(
        self,
        intent_id: str,
        *,
        verdict: str,
        reset: bool = False,
        passed: bool | None = False,
        check_passed: bool = False,
        detail: str = "missing",
        check_id: str = "output.contains.1",
    ) -> Path:
        path = self.root / f"{intent_id.replace(':', '-')}.json"
        body = {
            "schema": "prove.worker-result/1",
            "intent_id": intent_id,
            "evidence": {
                "schema": "prove.evidence/1",
                "id": evidence_id_for(intent_id),
                "intent_id": intent_id,
                "place_id": "example",
                "worker": "playtest",
                "captured_at": "2026-11-25T00:00:00Z",
                "verdict": verdict,
                "summary": detail,
                "observations": [],
                "artifacts": [],
                "limits": "Solo playtest.",
                "studio": {
                    "passed": passed,
                    "failures": [] if verdict != "fail" else [detail],
                    "checks": [
                        {
                            "id": check_id,
                            "op": "contains",
                            "expect": "hello from the agent",
                            "passed": check_passed,
                            "detail": detail,
                        }
                    ],
                    "console": {"reset": reset},
                },
            },
            "graph_patch": {"upsert_nodes": [], "upsert_edges": [], "set_status": []},
            "follow_ups": [],
        }
        path.write_text(json.dumps(body), encoding="utf-8")
        return path

    def attach(self, place: Place, intent_id: str, path: Path, verdict: str) -> None:
        place.nodes().append(
            {
                "id": evidence_id_for(intent_id),
                "type": "evidence",
                "name": verdict,
                "status": verdict,
                "props": {"path": path.as_posix(), "summary": detail_name(verdict)},
            }
        )

    def finish_verify(self, place: Place, *, claim: str, script: str = "observed") -> Path:
        place.node("intent:read-hello")["status"] = "done"
        place.node("intent:verify-hello")["status"] = "done"
        place.node("claim:hello-prints")["status"] = claim
        place.node("script:hello")["status"] = script
        if script == "observed":
            place.node("script:hello")["props"]["source_sha256"] = "abc"
        elif "source_sha256" in place.node("script:hello")["props"]:
            del place.node("script:hello")["props"]["source_sha256"]
        path = self.evidence("intent:verify-hello", verdict="fail" if claim == "contradicted" else "inconclusive")
        self.attach(place, "intent:verify-hello", path, "fail" if claim == "contradicted" else "inconclusive")
        if claim == "contradicted":
            place.data["edges"].append(
                {
                    "id": "edge:evidence:verify-hello:contradicts:claim:hello-prints",
                    "type": "contradicts",
                    "from": "evidence:verify-hello",
                    "to": "claim:hello-prints",
                }
            )
        return path

    def add_verify(self, place: Place, number: int, detail: str) -> None:
        intent_id = f"intent:verify-hello-{number}"
        place.nodes().append(
            {
                "id": intent_id,
                "type": "intent",
                "name": f"Verify {number}",
                "status": "done",
                "props": {
                    "goal_id": "goal:hello",
                    "worker": "playtest",
                    "action": "verify_output",
                    "summary": "Verify the hello line again.",
                    "inputs": {
                        "seconds": 3,
                        "screenshot": False,
                        "expect_contains": ["hello from the agent"],
                        "expect_absent": ["hello failed"],
                    },
                    "done_when": "Evidence verdict is pass for output.contains.1.",
                    "must_not": ["Edit any script.", "Save the place.", "Publish."],
                    "after": None,
                    "order": 2 + number,
                },
            }
        )
        place.data["edges"].append(
            {"id": f"edge:{intent_id}:goal", "type": "spawned_from", "from": intent_id, "to": "goal:hello"}
        )
        place.data["edges"].append(
            {"id": f"edge:{intent_id}:checks", "type": "checks", "from": intent_id, "to": "claim:hello-prints"}
        )
        path = self.evidence(intent_id, verdict="fail", detail=detail)
        self.attach(place, intent_id, path, "fail")


def detail_name(verdict: str) -> str:
    return verdict


class PlanTests(PlanCase):
    def test_ready_intent_is_left_in_place(self) -> None:
        place = self.place()
        before = place.path.read_bytes()
        result = plan(place)
        self.assertEqual(result.code, 0)
        self.assertFalse(result.changed)
        self.assertIn("next intent:read-hello script read_source (proposed)", result.lines)
        self.assertEqual(place.path.read_bytes(), before)

    def test_active_intent_blocks_a_new_plan(self) -> None:
        place = self.place()
        self.finish_verify(place, claim="contradicted")
        place.node("intent:read-hello")["status"] = "active"
        place.save()
        before = place.path.read_bytes()
        result = plan(place)
        self.assertEqual(result.code, 0)
        self.assertFalse(result.changed)
        self.assertIn("next intent:read-hello", result.lines[0])
        self.assertEqual(place.path.read_bytes(), before)
        self.assertIsNone(place.node("intent:fix-output-contains-1"))

    def test_blocked_intent_stops_planning(self) -> None:
        place = self.place()
        place.node("intent:read-hello")["status"] = "blocked"
        place.save()
        before = place.path.read_bytes()
        result = plan(place)
        self.assertEqual(result.code, 2)
        self.assertFalse(result.changed)
        self.assertIn("blocked intent:read-hello", result.lines[0])
        self.assertEqual(place.path.read_bytes(), before)

    def test_failed_check_adds_a_write_and_a_recheck(self) -> None:
        place = self.place()
        self.finish_verify(place, claim="contradicted")
        result = plan(place)
        saved = Place.load(place.path)
        write = next(intent for intent in saved.intents() if intent["props"]["action"] == "write_source")
        recheck = saved.node("intent:recheck-output-contains-1")
        assert recheck is not None
        self.assertEqual(result.code, 0)
        self.assertEqual(write["status"], "proposed")
        self.assertEqual(write["props"]["inputs"]["path"], HELLO)
        self.assertEqual(write["props"]["inputs"]["class_name"], "Script")
        self.assertNotIn("source", write["props"]["inputs"])
        self.assertIn("output.contains.1", write["props"]["summary"])
        self.assertLessEqual(len(write["props"]["summary"]), 200)
        self.assertEqual(recheck["props"]["after"], write["id"])
        self.assertEqual(recheck["props"]["inputs"]["expect_contains"], ["hello from the agent"])
        self.assertEqual(saved.claims_checked_by(write["id"]), [])
        self.assertEqual(saved.claims_checked_by(recheck["id"]), ["claim:hello-prints"])
        self.assertEqual(saved.node("claim:hello-prints")["status"], "contradicted")
        self.assertEqual(saved.node("goal:hello")["status"], "open")
        again = plan(saved)
        self.assertFalse(again.changed)
        self.assertIn(write["id"], again.lines[0])
        self.assertEqual(
            len([intent for intent in Place.load(place.path).intents() if intent["props"]["action"] == "write_source"]),
            1,
        )

    def test_stale_script_is_read_before_the_write(self) -> None:
        place = self.place()
        self.finish_verify(place, claim="contradicted", script="stale")
        plan(place)
        saved = Place.load(place.path)
        read = saved.node("intent:read-output-contains-1")
        write = saved.node("intent:fix-output-contains-1")
        recheck = saved.node("intent:recheck-output-contains-1")
        assert read is not None and write is not None and recheck is not None
        self.assertEqual(read["props"]["inputs"]["path"], HELLO)
        self.assertEqual(write["props"]["after"], read["id"])
        self.assertEqual(recheck["props"]["after"], write["id"])
        self.assertEqual(saved.next_intent()["id"], read["id"])

    def test_reset_replays_the_playtest_and_leaves_the_claim(self) -> None:
        place = self.place()
        place.node("intent:read-hello")["status"] = "done"
        place.node("intent:verify-hello")["status"] = "done"
        place.node("script:hello")["status"] = "observed"
        place.node("script:hello")["props"]["source_sha256"] = "abc"
        path = self.evidence(
            "intent:verify-hello",
            verdict="inconclusive",
            reset=True,
            passed=False,
            check_passed=False,
            detail="saw the whole log",
        )
        self.attach(place, "intent:verify-hello", path, "inconclusive")
        result = plan(place)
        saved = Place.load(place.path)
        replay = saved.node("intent:replay-output-contains-1")
        assert replay is not None
        self.assertEqual(result.code, 0)
        self.assertEqual(replay["props"]["action"], "verify_output")
        self.assertIsNone(replay["props"]["after"])
        self.assertIn("console.reset", replay["props"]["summary"])
        self.assertEqual(replay["props"]["inputs"]["expect_absent"], ["hello failed"])
        self.assertEqual(saved.claims_checked_by(replay["id"]), ["claim:hello-prints"])
        self.assertEqual(saved.node("claim:hello-prints")["status"], "unverified")
        self.assertFalse(any(intent["props"]["action"] == "write_source" for intent in saved.intents()))

    def test_readback_is_left_alone(self) -> None:
        place = self.place()
        self.finish_verify(place, claim="contradicted")
        place.nodes().append(
            {
                "id": "intent:verify-hello-readback",
                "type": "intent",
                "name": "Read back",
                "status": "proposed",
                "props": {
                    "goal_id": "goal:hello",
                    "worker": "script",
                    "action": "read_source",
                    "summary": "Read back HelloAgent.",
                    "inputs": {"path": HELLO},
                    "done_when": "The script has been read.",
                    "must_not": ["Repeat the call that may have landed.", "Save the place."],
                    "after": None,
                    "order": 3,
                },
            }
        )
        place.data["edges"].append(
            {
                "id": "edge:intent:verify-hello-readback:goal",
                "type": "spawned_from",
                "from": "intent:verify-hello-readback",
                "to": "goal:hello",
            }
        )
        place.save()
        before = place.path.read_bytes()
        result = plan(place)
        self.assertEqual(result.code, 0)
        self.assertFalse(result.changed)
        self.assertIn("intent:verify-hello-readback", result.lines[0])
        self.assertEqual(place.path.read_bytes(), before)

    def test_two_failures_still_plan_and_the_third_same_one_stops(self) -> None:
        place = self.place()
        self.finish_verify(place, claim="contradicted")
        self.add_verify(place, 2, "missing")
        planned = plan(place)
        self.assertEqual(planned.code, 0)
        self.assertIsNotNone(Place.load(place.path).node("intent:fix-output-contains-1"))

        stopped = self.place("third.local.json")
        self.finish_verify(stopped, claim="contradicted")
        self.add_verify(stopped, 2, "missing")
        self.add_verify(stopped, 3, "missing")
        result = plan(stopped)
        saved = Place.load(stopped.path)
        self.assertEqual(result.code, 2)
        self.assertIsNone(saved.node("intent:fix-output-contains-1"))
        question = saved.node("question:hello-prints-stuck")
        blocked = saved.node("intent:stop-output-contains-1")
        assert question is not None and blocked is not None
        self.assertEqual(question["status"], "open")
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(saved.node("claim:hello-prints")["status"], "contradicted")
        self.assertEqual(saved.node("goal:hello")["status"], "open")
        again = plan(saved)
        self.assertEqual(again.code, 2)
        self.assertFalse(again.changed)
        self.assertEqual(
            len([node for node in Place.load(stopped.path).nodes() if node["type"] == "question"]),
            2,
        )

    def test_a_new_observation_is_planned_again(self) -> None:
        place = self.place()
        self.finish_verify(place, claim="contradicted")
        self.add_verify(place, 2, "missing")
        self.add_verify(place, 3, "a different console line")
        result = plan(place)
        self.assertEqual(result.code, 0)
        self.assertIsNotNone(Place.load(place.path).node("intent:fix-output-contains-1"))

    def test_missing_evidence_file_does_not_invent_an_intent(self) -> None:
        place = self.place()
        place.node("intent:read-hello")["status"] = "done"
        place.node("intent:verify-hello")["status"] = "done"
        place.save()
        before = place.path.read_bytes()
        result = plan(place)
        self.assertEqual(result.code, 2)
        self.assertFalse(result.changed)
        self.assertIn("missing evidence file for intent:verify-hello", result.lines)
        self.assertEqual(place.path.read_bytes(), before)

    def test_supported_claims_close_the_goal(self) -> None:
        place = self.place()
        place.node("intent:read-hello")["status"] = "done"
        place.node("intent:verify-hello")["status"] = "done"
        place.node("claim:hello-prints")["status"] = "supported"
        result = plan(place)
        saved = Place.load(place.path)
        self.assertEqual(result.code, 0)
        self.assertEqual(saved.node("goal:hello")["status"], "done")
        self.assertIn("goal:hello done", result.lines)
        self.assertIn("nothing to add", result.lines)

    def test_no_script_path_starts_with_overview(self) -> None:
        place = self.place()
        self.finish_verify(place, claim="contradicted")
        place.node("script:hello")["props"].pop("path")
        place.node("intent:read-hello")["props"]["inputs"] = {}
        plan(place)
        saved = Place.load(place.path)
        actions = [intent["props"]["action"] for intent in saved.intents() if intent["status"] == "proposed"]
        self.assertEqual(actions[0], "overview")
        self.assertNotIn("write_source", actions)

    def test_long_failure_detail_fits_the_summary_limit(self) -> None:
        place = self.place()
        place.node("intent:read-hello")["status"] = "done"
        place.node("intent:verify-hello")["status"] = "done"
        place.node("claim:hello-prints")["status"] = "contradicted"
        place.node("script:hello")["status"] = "observed"
        place.node("script:hello")["props"]["source_sha256"] = "abc"
        path = self.evidence("intent:verify-hello", verdict="fail", detail="x" * 500)
        self.attach(place, "intent:verify-hello", path, "fail")
        plan(place)
        write = next(
            intent for intent in Place.load(place.path).intents() if intent["props"]["action"] == "write_source"
        )
        self.assertLessEqual(len(write["props"]["summary"]), 200)
        self.assertTrue(write["props"]["summary"].endswith("…"))

    def test_sample_file_is_not_rewritten(self) -> None:
        place = self.place("example.place.json")
        self.finish_verify(place, claim="contradicted")
        place.save()
        before = place.path.read_bytes()
        result = plan(place)
        self.assertEqual(result.code, 2)
        self.assertIn("local.json", result.lines[0])
        self.assertEqual(place.path.read_bytes(), before)
        self.assertIsNone(place.node("intent:fix-output-contains-1"))

    def test_module_plan_leaves_the_checked_in_sample(self) -> None:
        before = EXAMPLE.read_bytes()
        code = main(["plan", str(EXAMPLE)])
        self.assertEqual(code, 0)
        self.assertEqual(EXAMPLE.read_bytes(), before)

    def test_run_leaves_a_write_proposed_until_source_is_set(self) -> None:
        place = self.place()
        place.node("intent:verify-hello")["status"] = "rejected"
        intent = place.node("intent:read-hello")
        intent["props"]["action"] = "write_source"
        intent["props"]["inputs"] = {"path": HELLO}
        place.save()

        def connect(**kwargs):
            raise AssertionError("Studio was contacted")

        with mock.patch("roblox_studio_adapter.RobloxStudio.connect", connect):
            code = main(["run", str(place.path), "--name", "X"])
        self.assertEqual(code, 2)
        saved = Place.load(place.path)
        self.assertEqual(saved.node("intent:read-hello")["status"], "proposed")
        with self.assertRaises(NeedPerson):
            run_intent(place, object())
        self.assertEqual(Place.load(place.path).node("intent:read-hello")["status"], "proposed")


if __name__ == "__main__":
    unittest.main()
