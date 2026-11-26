"""Session loop tests. They edit place files and do not open Studio."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from prove.admit import add_goal, answer_question, fill_source, init_place  # noqa: E402
from prove.brief import brief  # noqa: E402
from prove.cli import main  # noqa: E402
from prove.graph import Place, PlaceError  # noqa: E402
from prove.planner import plan  # noqa: E402

EXAMPLE = ROOT / "graph" / "places" / "example.place.json"


class LoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_init_goal_and_plan_prepare_a_read(self) -> None:
        dest = self.root / "game.local.json"
        self.assertEqual(
            main(["init", str(dest), "--id", "game", "--title", "Game", "--display-name", "Game Place"]),
            0,
        )
        self.assertEqual(
            main(
                [
                    "goal",
                    str(dest),
                    "--statement",
                    "The server prints ready.",
                    "--contains",
                    "ready",
                    "--script",
                    "game.ServerScriptService.Ready",
                    "--name",
                    "Ready",
                ]
            ),
            0,
        )
        self.assertEqual(main(["plan", str(dest)]), 0)
        place = Place.load(dest)
        nxt = place.next_intent()
        assert nxt is not None
        self.assertEqual(nxt["props"]["action"], "read_source")
        self.assertEqual(nxt["props"]["inputs"]["path"], "game.ServerScriptService.Ready")
        self.assertEqual(brief(place)["action"], "run")
        self.assertEqual(brief(place)["intent"], nxt["id"])
        before = dest.read_bytes()
        self.assertEqual(main(["plan", str(dest)]), 0)
        self.assertEqual(dest.read_bytes(), before)

    def test_goal_without_a_script_explores_once(self) -> None:
        dest = self.root / "bare.local.json"
        init_place(dest, "bare", "Bare", "Bare Place")
        place = Place.load(dest)
        add_goal(
            place,
            statement="Something prints.",
            contains=["ready"],
            absent=[],
            script=None,
            class_name="Script",
            seconds=3,
            name="Something",
        )
        place.save()
        result = plan(place)
        self.assertIn("explore overview", result.lines[0])
        saved = Place.load(dest)
        overview = saved.next_intent()
        assert overview is not None
        overview["status"] = "done"
        saved.save()
        again = plan(saved)
        self.assertFalse(again.changed)
        self.assertIn("need script path", again.lines[0])
        blocked = brief(Place.load(dest))
        self.assertEqual(blocked["action"], "blocked")
        self.assertIn("need script path", blocked["reason"])
        intents = Place.load(dest).intents()
        self.assertEqual(len([intent for intent in intents if intent["props"]["action"] == "overview"]), 1)

    def test_question_blocks_fill_until_it_is_answered(self) -> None:
        from prove.records import evidence_id_for

        place_path = self.root / "game.local.json"
        init_place(place_path, "game", "Game", "Game Place")
        place = Place.load(place_path)
        add_goal(
            place,
            statement="The server prints ready.",
            contains=["ready"],
            absent=[],
            script="game.ServerScriptService.Ready",
            class_name="Script",
            seconds=3,
            name="Ready",
        )
        place.nodes().append(
            {
                "id": "question:which-window",
                "type": "question",
                "name": "Which window",
                "status": "open",
                "props": {"text": "Which Studio window?"},
            }
        )
        place.data["edges"].append(
            {
                "id": "edge:question:which-window:about",
                "type": "about",
                "from": "question:which-window",
                "to": "place:game",
            }
        )
        place.save()
        plan(place)
        saved = Place.load(place_path)
        read = saved.next_intent()
        assert read is not None
        read["status"] = "done"
        script = next(node for node in saved.nodes() if node["type"] == "script")
        script["status"] = "observed"
        script["props"]["source_sha256"] = "abc"
        source_path = self.root / "read.json"
        source_path.write_text(
            '{"schema":"prove.worker-result/1","evidence":{"intent_id":"%s","observations":['
            '{"kind":"script_path","text":"game.ServerScriptService.Ready"},'
            '{"kind":"source","text":"print(1)\\n"}]}}' % read["id"],
            encoding="utf-8",
        )
        saved.nodes().append(
            {
                "id": evidence_id_for(read["id"]),
                "type": "evidence",
                "name": "read",
                "status": "inconclusive",
                "props": {"path": source_path.as_posix(), "summary": "Read Ready."},
            }
        )
        verify = next(intent for intent in saved.intents() if intent["props"]["action"] == "verify_output")
        verify["status"] = "done"
        saved.node(saved.claims_checked_by(verify["id"])[0])["status"] = "contradicted"
        fail_path = self.root / "fail.json"
        fail_path.write_text(
            '{"schema":"prove.worker-result/1","evidence":{"schema":"prove.evidence/1","verdict":"fail",'
            '"intent_id":"%s","observations":[],"studio":{"passed":false,"failures":["missing"],'
            '"checks":[{"id":"output.contains.1","passed":false,"detail":"missing","expect":"ready"}],'
            '"console":{"reset":false}}}}' % verify["id"],
            encoding="utf-8",
        )
        saved.nodes().append(
            {
                "id": evidence_id_for(verify["id"]),
                "type": "evidence",
                "name": "fail",
                "status": "fail",
                "props": {"path": fail_path.as_posix(), "summary": "missing"},
            }
        )
        saved.save()
        plan(saved)
        planned = Place.load(place_path)
        write = next(intent for intent in planned.intents() if intent["props"]["action"] == "write_source")
        self.assertEqual(brief(planned)["action"], "answer")
        with self.assertRaises(PlaceError):
            fill_source(planned, write["id"], "print(1)\n")
        answer_question(planned, "question:which-window", "Game Place")
        planned.save()
        answered = Place.load(place_path)
        payload = brief(answered)
        self.assertEqual(payload["action"], "fill")
        self.assertEqual(payload["source"], "print(1)\n")
        body = self.root / "body.lua"
        body.write_text("print('fixed')\n", encoding="utf-8")
        self.assertEqual(main(["fill", str(place_path), write["id"], "--file", str(body)]), 0)
        filled = Place.load(place_path)
        self.assertEqual(filled.node(write["id"])["props"]["inputs"]["source"], "print('fixed')\n")
        self.assertEqual(brief(filled)["action"], "run")

    def test_sample_file_stays_unchanged(self) -> None:
        before = EXAMPLE.read_bytes()
        place = Place.load(EXAMPLE)
        self.assertEqual(brief(place)["action"], "run")
        self.assertEqual(brief(place)["intent"], "intent:read-hello")
        self.assertEqual(main(["next", str(EXAMPLE)]), 0)
        self.assertEqual(main(["goal", str(EXAMPLE), "--statement", "x", "--contains", "y"]), 2)
        self.assertEqual(EXAMPLE.read_bytes(), before)
