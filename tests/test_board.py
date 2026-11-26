"""Place board tests. They read place files and do not open a browser or Studio."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from prove.admit import init_place  # noqa: E402
from prove.board import evidence_view, list_places, place_board, resolve_place  # noqa: E402
from prove.graph import Place, PlaceError  # noqa: E402
from prove.records import evidence_id_for  # noqa: E402
from prove.ui import handle_api, make_server  # noqa: E402

EXAMPLE = ROOT / "graph" / "places" / "example.place.json"
SENTINEL = "SENTINEL_SOURCE_SHOULD_NOT_LEAK"


class BoardTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "AGENTS.md").write_text("agent\n", encoding="utf-8")
        (self.root / "protocols").mkdir()
        (self.root / "graph" / "places").mkdir(parents=True)

    def test_example_board_names_the_read_and_hides_nothing_it_does_not_have(self) -> None:
        dest = self.root / "graph" / "places" / "example.place.json"
        dest.write_bytes(EXAMPLE.read_bytes())
        board = place_board(Place.load(dest))
        self.assertEqual(board["brief"]["action"], "run")
        self.assertEqual(board["brief"]["intent"], "intent:read-hello")
        self.assertNotIn("source", board["brief"])
        self.assertEqual(board["claims"][0]["id"], "claim:hello-prints")
        self.assertIn("contains hello from the agent", board["claims"][0]["check"])
        self.assertEqual(board["intents"][0]["id"], "intent:read-hello")
        self.assertEqual(board["next_intent"], "intent:read-hello")

    def test_evidence_view_drops_the_script_body(self) -> None:
        dest = self.root / "graph" / "places" / "game.local.json"
        init_place(dest, "game", "Game", "Game Place")
        place = Place.load(dest)
        source = self.root / "evidence" / "runs" / "intent-read-ready.worker-result.json"
        source.parent.mkdir(parents=True)
        source.write_text(
            json.dumps(
                {
                    "schema": "prove.worker-result/1",
                    "evidence": {
                        "intent_id": "intent:read-ready",
                        "verdict": "inconclusive",
                        "summary": "Read Ready.",
                        "limits": "Local file.",
                        "observations": [
                            {"kind": "script_path", "text": "game.ServerScriptService.Ready"},
                            {"kind": "source_sha256", "text": "abc"},
                            {"kind": "source", "text": SENTINEL},
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )
        place.nodes().append(
            {
                "id": evidence_id_for("intent:read-ready"),
                "type": "evidence",
                "name": "read",
                "status": "inconclusive",
                "props": {"path": "evidence/runs/intent-read-ready.worker-result.json", "summary": "Read Ready."},
            }
        )
        place.nodes().append(
            {
                "id": "intent:read-ready",
                "type": "intent",
                "name": "Read",
                "status": "done",
                "props": {
                    "goal_id": "goal:missing",
                    "worker": "script",
                    "action": "read_source",
                    "summary": "Read Ready.",
                    "inputs": {"path": "game.ServerScriptService.Ready", "source": SENTINEL},
                    "done_when": "Read.",
                    "must_not": ["Save the place."],
                    "after": None,
                    "order": 1,
                },
            }
        )
        view = evidence_view(place, "intent:read-ready")
        blob = json.dumps(view)
        self.assertNotIn(SENTINEL, blob)
        self.assertNotIn("source", [item["kind"] for item in view["observations"]])
        self.assertEqual(view["observations"][1]["text"], "abc")
        board = json.dumps(place_board(place))
        self.assertNotIn(SENTINEL, board)

    def test_place_names_cannot_leave_the_places_folder(self) -> None:
        with self.assertRaises(PlaceError):
            resolve_place(self.root, "../AGENTS.md")
        with self.assertRaises(PlaceError):
            resolve_place(self.root, "nested/game.local.json")

    def test_api_goal_updates_the_board_and_plan_does_not_call_studio(self) -> None:
        dest = self.root / "graph" / "places" / "game.local.json"
        init_place(dest, "game", "Game", "Game Place")
        status, payload = handle_api(
            "POST",
            "/api/goal",
            {},
            {
                "file": "game.local.json",
                "statement": "The server prints ready.",
                "contains": "ready",
                "script": "game.ServerScriptService.Ready",
                "name": "Ready",
            },
            self.root,
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["board"]["claims"][0]["path"], "game.ServerScriptService.Ready")
        status, planned = handle_api("POST", "/api/plan", {}, {"file": "game.local.json"}, self.root)
        self.assertEqual(status, 200)
        self.assertEqual(planned["board"]["brief"]["action"], "run")
        self.assertEqual(planned["board"]["next_intent"], "intent:read-ready")
        files = list_places(self.root)
        self.assertEqual(files[0]["file"], "game.local.json")

    def test_static_board_serves_the_page_and_refuses_a_missing_asset(self) -> None:
        page = self.root / "web" / "static"
        (page / "assets").mkdir(parents=True)
        (page / "index.html").write_text("<!doctype html><title>PROVE</title><p>board</p>", encoding="utf-8")
        (page / "assets" / "app.css").write_text("body{}", encoding="utf-8")
        server = make_server(self.root, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def get(path: str) -> tuple[int, str, str]:
            try:
                with urllib.request.urlopen(base + path) as response:
                    return response.status, response.headers.get("Content-Type", ""), response.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                try:
                    return exc.code, exc.headers.get("Content-Type", ""), exc.read().decode("utf-8")
                finally:
                    exc.close()

        status, mime, body = get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", mime)
        self.assertIn("board", body)
        status, mime, body = get("/goals")
        self.assertEqual(status, 200)
        self.assertIn("board", body)
        status, mime, _body = get("/assets/app.css")
        self.assertEqual(status, 200)
        self.assertIn("text/css", mime)
        status, _mime, _body = get("/assets/missing.js")
        self.assertEqual(status, 404)
        with self.assertRaises(PlaceError):
            make_server(self.root, "0.0.0.0", 0)

    def test_jetpack_read_keeps_the_module_body_off_the_board(self) -> None:
        local = ROOT / "graph" / "places" / "jetpack-mania.local.json"
        if not local.is_file():
            self.skipTest("local place is not on this machine")
        place = Place.load(local)
        board = place_board(place)
        self.assertEqual(board["id"], "jetpack-mania")
        self.assertEqual(board["brief"]["action"], "done")
        claim = next(item for item in board["claims"] if item["id"] == "claim:map")
        self.assertEqual(claim["status"], "supported")
        self.assertIn("simulation-present", claim["check"])
        view = evidence_view(place, "intent:read-simulation")
        blob = json.dumps({"board": board, "evidence": view})
        self.assertNotIn("function Simulation", blob)
        self.assertNotIn('"kind": "source"', blob)
        self.assertFalse(view["missing"])
