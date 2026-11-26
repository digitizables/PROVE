"""Fakes only. These tests do not open Roblox Studio."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / "roblox-studio-adapter" / "src"))
sys.path.insert(0, str(ROOT / "src"))

from prove.cli import main, run_studio  # noqa: E402
from prove.graph import Place, PlaceError  # noqa: E402
from prove.session import UnsupportedIntent, run_intent  # noqa: E402
from prove.verdict import verdict_from_studio  # noqa: E402
from roblox_studio_adapter.errors import (  # noqa: E402
    AmbiguousOutcome,
    AmbiguousStudioError,
    TimeoutError,
    ToolFailed,
)
from roblox_studio_adapter.results import CheckResult, ConsoleDelta, PlaytestReport, ScriptWriteResult  # noqa: E402

EXAMPLE = ROOT / "graph" / "places" / "example.place.json"
SENTINEL = "SENTINEL_SOURCE_SHOULD_NOT_LEAK\n"


class PlaceCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def place(self, name: str = "game.local.json") -> Place:
        dest = self.root / name
        shutil.copy(EXAMPLE, dest)
        return Place.load(dest)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def play_report(*, passed: bool | None, reset: bool = False, failures: list[str] | None = None) -> PlaytestReport:
    failed = passed is False
    return PlaytestReport(
        mode_before="Edit",
        mode_after="Edit",
        started=True,
        stopped=True,
        seconds=3,
        console=ConsoleDelta(text="hello from the agent\n", reset=reset),
        passed=passed,
        failures=list(failures if failures is not None else (["missing hello"] if failed else [])),
        checks=[
            CheckResult(
                "output.contains.1",
                "contains",
                "hello from the agent",
                passed is True,
                "found" if passed is True else "missing",
            )
        ],
    )


class Reader:
    def __init__(self, source: str) -> None:
        self.reads: list[str] = []
        self.source = source
        self.scripts = self

    def read(self, path: str):
        self.reads.append(path)
        return SimpleNamespace(source=self.source)


class Boom:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.scripts = self

    def read(self, path: str):
        raise self.exc


class Player:
    def __init__(self, report: PlaytestReport) -> None:
        self.session = SimpleNamespace(studio_id="studio-1")
        self.playtest = self
        self.kwargs = None
        self.report = report

    def run(self, **kwargs):
        self.kwargs = kwargs
        return self.report


class GraphTests(PlaceCase):
    def test_example_runs_the_read_before_the_playtest(self) -> None:
        place = self.place()
        self.assertEqual(place.next_intent()["id"], "intent:read-hello")
        place.node("intent:read-hello")["status"] = "done"
        self.assertEqual(place.next_intent()["id"], "intent:verify-hello")

    def test_active_intent_is_the_only_next_step(self) -> None:
        place = self.place()
        place.node("intent:verify-hello")["status"] = "active"
        self.assertEqual(place.next_intent()["id"], "intent:verify-hello")

    def test_two_active_intents_are_refused(self) -> None:
        place = self.place()
        place.node("intent:read-hello")["status"] = "active"
        place.node("intent:verify-hello")["status"] = "active"
        with self.assertRaises(PlaceError):
            place.next_intent()

    def test_rejected_predecessor_does_not_release_the_next_intent(self) -> None:
        place = self.place()
        place.node("intent:read-hello")["status"] = "rejected"
        self.assertIsNone(place.next_intent())

    def test_goal_closes_when_the_checked_claim_is_supported(self) -> None:
        place = self.place()
        place.node("intent:read-hello")["status"] = "done"
        place.node("intent:verify-hello")["status"] = "done"
        place.node("claim:hello-prints")["status"] = "supported"
        place.close_goals()
        self.assertEqual(place.node("goal:hello")["status"], "done")

    def test_goal_stays_open_while_the_claim_is_unverified(self) -> None:
        place = self.place()
        place.node("intent:read-hello")["status"] = "done"
        place.node("intent:verify-hello")["status"] = "done"
        place.close_goals()
        self.assertEqual(place.node("goal:hello")["status"], "open")


class VerdictTests(unittest.TestCase):
    def test_reset_wins_over_the_passed_flag(self) -> None:
        self.assertEqual(verdict_from_studio({"passed": True, "console": {"reset": True}}), "inconclusive")
        self.assertEqual(verdict_from_studio({"passed": False, "console": {"reset": True}}), "inconclusive")
        self.assertEqual(verdict_from_studio({"passed": True, "console": {"reset": False}}), "pass")
        self.assertEqual(verdict_from_studio({"passed": False, "console": {"reset": False}}), "fail")
        self.assertEqual(verdict_from_studio({"passed": None, "console": {"reset": False}}), "inconclusive")


class SessionTests(PlaceCase):
    def test_read_records_the_hash_and_leaves_the_body_in_studio(self) -> None:
        place = self.place()
        agent = Reader(SENTINEL)
        result = run_intent(place, agent)
        saved = Place.load(place.path)
        script = saved.node("script:hello")
        assert script is not None
        self.assertEqual(script["status"], "observed")
        self.assertEqual(script["props"]["source_sha256"], digest(SENTINEL))
        self.assertNotIn("source", script["props"])
        self.assertEqual(saved.node("intent:read-hello")["status"], "done")
        self.assertEqual(saved.node("intent:verify-hello")["status"], "proposed")
        self.assertEqual(saved.node("claim:hello-prints")["status"], "unverified")
        self.assertEqual(saved.node("goal:hello")["status"], "open")
        self.assertEqual(result["evidence"]["verdict"], "inconclusive")
        evidence_path = self.root / "evidence-runs" / "intent-read-hello.worker-result.json"
        text = evidence_path.read_text(encoding="utf-8")
        self.assertNotIn(SENTINEL.strip(), text)
        self.assertNotIn(SENTINEL.strip(), place.path.read_text(encoding="utf-8"))
        self.assertEqual(json.loads(text)["schema"], "prove.worker-result/1")
        self.assertEqual(agent.reads, ["game.ServerScriptService.HelloAgent"])

    def test_unsupported_action_does_not_activate(self) -> None:
        place = self.place()
        place.node("intent:read-hello")["props"]["action"] = "grep"
        with self.assertRaises(UnsupportedIntent):
            run_intent(place, Reader(SENTINEL))
        saved = Place.load(place.path)
        self.assertEqual(saved.node("intent:read-hello")["status"], "proposed")
        self.assertEqual(saved.node("intent:read-hello")["props"]["action"], "read_source")

    def test_unexpected_error_leaves_the_intent_active(self) -> None:
        place = self.place()
        with self.assertRaises(RuntimeError):
            run_intent(place, Boom(RuntimeError("studio blew up")))
        saved = Place.load(place.path)
        self.assertEqual(saved.node("intent:read-hello")["status"], "active")
        self.assertEqual(list(self.root.joinpath("evidence-runs").glob("*.json")), [])

    def test_tool_failure_is_a_fail_and_does_not_touch_an_unchecked_claim(self) -> None:
        place = self.place()
        result = run_intent(place, Boom(ToolFailed("script_read", "missing")))
        saved = Place.load(place.path)
        self.assertEqual(result["evidence"]["verdict"], "fail")
        self.assertEqual(result["follow_ups"], [])
        self.assertEqual(saved.node("intent:read-hello")["status"], "done")
        self.assertEqual(saved.node("claim:hello-prints")["status"], "unverified")

    def test_ambiguous_write_proposes_a_read(self) -> None:
        for exc in (AmbiguousOutcome("multi_edit"), TimeoutError("timed out")):
            with self.subTest(kind=type(exc).__name__):
                place = self.place(f"{type(exc).__name__}.local.json")
                intent = place.node("intent:read-hello")
                intent["props"]["action"] = "write_source"
                intent["props"]["inputs"] = {
                    "path": "game.ServerScriptService.HelloAgent",
                    "source": "print(1)\r\n",
                }

                class Writer:
                    def __init__(self) -> None:
                        self.scripts = self

                    def write(self, path: str, source: str, class_name: str = "auto") -> None:
                        raise exc

                result = run_intent(place, Writer())
                saved = Place.load(place.path)
                follow = result["follow_ups"][0]
                self.assertEqual(result["evidence"]["verdict"], "inconclusive")
                self.assertEqual(saved.node("intent:read-hello")["status"], "done")
                self.assertEqual(saved.node("claim:hello-prints")["status"], "unverified")
                self.assertEqual(saved.node("goal:hello")["status"], "open")
                self.assertEqual(follow["status"], "proposed")
                self.assertEqual(follow["props"]["action"], "read_source")
                self.assertEqual(follow["props"]["inputs"]["path"], "game.ServerScriptService.HelloAgent")
                self.assertEqual(saved.node(follow["id"])["status"], "proposed")
                self.assertNotIn("source_sha256", saved.node("script:hello")["props"])

    def test_verify_pass_fail_and_reset(self) -> None:
        cases = [
            (True, False, "pass", "supported", "supports"),
            (False, False, "fail", "contradicted", "contradicts"),
            (False, True, "inconclusive", "unverified", None),
        ]
        for passed, reset, verdict, claim, relation in cases:
            with self.subTest(verdict=verdict):
                place = self.place(f"{verdict}.local.json")
                place.node("intent:read-hello")["status"] = "done"
                probes = [{"id": "base", "expression": "workspace.Baseplate", "datamodel": "Server"}]
                place.node("intent:verify-hello")["props"]["inputs"]["probes"] = probes
                agent = Player(play_report(passed=passed, reset=reset))
                result = run_intent(place, agent)
                saved = Place.load(place.path)
                self.assertEqual(result["evidence"]["verdict"], verdict)
                self.assertEqual(saved.node("claim:hello-prints")["status"], claim)
                self.assertEqual(saved.node("intent:verify-hello")["status"], "done")
                self.assertEqual(agent.kwargs["probes"], probes)
                self.assertFalse(agent.kwargs["screenshot"])
                edge_types = [edge["type"] for edge in result["graph_patch"]["upsert_edges"]]
                if relation is None:
                    self.assertNotIn("supports", edge_types)
                    self.assertNotIn("contradicts", edge_types)
                    self.assertEqual(saved.node("goal:hello")["status"], "open")
                else:
                    self.assertIn(relation, edge_types)

    def test_read_then_pass_closes_the_goal(self) -> None:
        place = self.place()
        run_intent(place, Reader(SENTINEL))
        self.assertEqual(place.node("goal:hello")["status"], "open")
        run_intent(place, Player(play_report(passed=True)))
        saved = Place.load(place.path)
        self.assertEqual(saved.node("claim:hello-prints")["status"], "supported")
        self.assertEqual(saved.node("goal:hello")["status"], "done")
        self.assertEqual(saved.node("intent:verify-hello")["status"], "done")

    def test_overview_observes_scripts_without_inventing_a_hash(self) -> None:
        place = self.place()
        place.node("script:hello")["props"]["source_sha256"] = "abc"
        intent = place.node("intent:read-hello")
        intent["props"]["worker"] = "explore"
        intent["props"]["action"] = "overview"
        intent["props"]["inputs"] = {}

        class Explorer:
            def __init__(self) -> None:
                self.loop = self

            def explore(self):
                return {
                    "services": {
                        "ServerScriptService": [
                            "Script ServerScriptService.HelloAgent",
                            "Folder ServerScriptService.Stuff",
                        ],
                        "ReplicatedStorage": ["ModuleScript ReplicatedStorage.Util"],
                    },
                    "truncated": ["Workspace"],
                }

        result = run_intent(place, Explorer())
        saved = Place.load(place.path)
        hello = saved.node("script:hello")
        assert hello is not None
        self.assertEqual(hello["props"]["source_sha256"], "abc")
        self.assertNotIn("source", hello["props"])
        util = saved.node("script:replicatedstorage-util")
        assert util is not None
        self.assertEqual(util["props"]["path"], "game.ReplicatedStorage.Util")
        self.assertEqual(util["props"]["class_name"], "ModuleScript")
        self.assertNotIn("source_sha256", util["props"])
        self.assertEqual(saved.node("service:serverscriptservice")["status"], "observed")
        self.assertEqual(saved.node("service:replicatedstorage")["name"], "ReplicatedStorage")
        self.assertIn("Truncated: Workspace", result["evidence"]["limits"])
        self.assertEqual(result["evidence"]["verdict"], "inconclusive")

    def test_change_and_verify_hashes_the_written_source(self) -> None:
        place = self.place()
        for intent in place.intents():
            intent["status"] = "rejected"
        source = "SENTINEL_WRITE\r\nprint(1)\r\n"
        place.nodes().append(
            {
                "id": "intent:fix-hello",
                "type": "intent",
                "name": "Fix hello",
                "status": "proposed",
                "props": {
                    "goal_id": "goal:hello",
                    "worker": "playtest",
                    "action": "change_and_verify",
                    "summary": "Write HelloAgent and playtest the line.",
                    "inputs": {
                        "scripts": [
                            {
                                "path": "game.ServerScriptService.HelloAgent",
                                "source": source,
                                "class_name": "Script",
                            }
                        ],
                        "instances": [{"name": "Marker", "class_name": "Part"}],
                        "seconds": 3,
                        "probes": [{"id": "ready", "expression": "true", "datamodel": "Server", "equals": True}],
                    },
                    "done_when": "The playtest passes.",
                    "must_not": ["Save the place."],
                    "after": None,
                    "order": 3,
                },
            }
        )
        place.data["edges"].append(
            {"id": "edge:fix-goal", "type": "spawned_from", "from": "intent:fix-hello", "to": "goal:hello"}
        )
        place.data["edges"].append(
            {"id": "edge:fix-claim", "type": "checks", "from": "intent:fix-hello", "to": "claim:hello-prints"}
        )
        seen = {}

        class Changer:
            def __init__(self) -> None:
                self.loop = self
                self.session = SimpleNamespace(studio_id="studio-1")

            def change_and_verify(self, **kwargs):
                seen.update(kwargs)
                from roblox_studio_adapter.evidence import evidence_record

                return {
                    "scripts": [
                        ScriptWriteResult(
                            path="game.ServerScriptService.HelloAgent",
                            created=False,
                            unchanged=False,
                            class_name="Script",
                        )
                    ],
                    "instances": ["Workspace.Marker"],
                    "evidence": evidence_record(play_report(passed=True), studio_id="studio-1", intent_id=kwargs["intent_id"]),
                }

        result = run_intent(place, Changer())
        saved = Place.load(place.path)
        script = saved.node("script:hello")
        assert script is not None
        self.assertEqual(script["props"]["source_sha256"], digest("SENTINEL_WRITE\nprint(1)\n"))
        self.assertNotIn("source", script["props"])
        marker = saved.node("instance:workspace-marker")
        assert marker is not None
        self.assertEqual(marker["props"]["class_name"], "Part")
        self.assertEqual(result["evidence"]["verdict"], "pass")
        self.assertEqual(saved.node("claim:hello-prints")["status"], "supported")
        self.assertEqual(saved.node("goal:hello")["status"], "done")
        self.assertEqual(seen["intent_id"], "intent:fix-hello")
        self.assertEqual(seen["probes"][0]["id"], "ready")
        evidence = next(node for node in result["graph_patch"]["upsert_nodes"] if node["type"] == "evidence")
        self.assertNotIn("SENTINEL_WRITE", Path(evidence["props"]["path"]).read_text(encoding="utf-8"))


class CliTests(PlaceCase):
    def test_status_module_leaves_the_sample_unchanged(self) -> None:
        before = EXAMPLE.read_bytes()
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), env.get("PYTHONPATH", "")])
        proc = subprocess.run(
            [sys.executable, "-m", "prove", "status", str(EXAMPLE)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("next intent:read-hello script read_source (proposed)", proc.stdout)
        self.assertIn("waiting intent:verify-hello after intent:read-hello", proc.stdout)
        self.assertIn("question:which-studio:", proc.stdout)
        run = subprocess.run(
            [sys.executable, "-m", "prove", "run", str(EXAMPLE)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(run.returncode, 2, run.stderr)
        self.assertIn(".local.json", run.stderr)
        self.assertEqual(EXAMPLE.read_bytes(), before)

    def test_ambiguous_window_blocks_the_intent(self) -> None:
        place = self.place()
        seen: dict = {}

        def connect(**kwargs):
            seen.update(kwargs)
            raise AmbiguousStudioError([{"id": "a", "name": "A"}, {"id": "b", "name": "B"}])

        with mock.patch("roblox_studio_adapter.RobloxStudio.connect", connect):
            result = run_studio(place, name=None, studio_id=None)
        saved = Place.load(place.path)
        self.assertEqual(seen, {"name_contains": "Example"})
        self.assertEqual(result["evidence"]["verdict"], "blocked")
        self.assertEqual(saved.node("intent:read-hello")["status"], "blocked")

    def test_studio_id_overrides_the_display_name(self) -> None:
        place = self.place("picked.local.json")
        seen: dict = {}

        def connect(**kwargs):
            seen.update(kwargs)
            raise AmbiguousStudioError([{"id": "a", "name": "A"}, {"id": "b", "name": "B"}])

        with mock.patch("roblox_studio_adapter.RobloxStudio.connect", connect):
            code = main(["run", str(place.path), "--name", "Nope", "--studio-id", "abc"])
        self.assertEqual(code, 2)
        self.assertEqual(seen, {"studio_id": "abc"})
        self.assertEqual(Place.load(place.path).node("intent:read-hello")["status"], "blocked")

    def test_unsupported_cli_does_not_connect(self) -> None:
        place = self.place("manual.local.json")
        place.node("intent:read-hello")["props"]["action"] = "grep"
        place.save()

        def connect(**kwargs):
            raise AssertionError("connect should not run")

        with mock.patch("roblox_studio_adapter.RobloxStudio.connect", connect):
            code = main(["run", str(place.path), "--name", "X"])
        self.assertEqual(code, 2)
        saved = Place.load(place.path)
        self.assertEqual(saved.node("intent:read-hello")["status"], "proposed")
        self.assertEqual(saved.node("intent:read-hello")["props"]["action"], "grep")


if __name__ == "__main__":
    unittest.main()
