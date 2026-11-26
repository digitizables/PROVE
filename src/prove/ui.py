"""Local place board. Serves the graph to the browser and does not call Studio."""

from __future__ import annotations

import json
import mimetypes
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from prove.admit import add_goal, answer_question, bind_claim
from prove.board import evidence_view, list_places, place_board, resolve_place
from prove.graph import Place, PlaceError
from prove.planner import plan
from prove.session import locate_root

_MAX_BODY = 256 * 1024
_LOOPBACK = {"127.0.0.1", "localhost"}
_STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".json": "application/json; charset=utf-8",
}


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def static_dir(root: Path) -> Path | None:
    folder = root / "web" / "static"
    if (folder / "index.html").is_file():
        return folder
    return None


def make_server(root: Path, host: str, port: int) -> ThreadingHTTPServer:
    if host not in _LOOPBACK:
        raise PlaceError("The place board listens on 127.0.0.1 only")
    folder = root.resolve()
    static = static_dir(folder)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802
            self._dispatch()

        def do_POST(self) -> None:  # noqa: N802
            self._dispatch()

        def _dispatch(self) -> None:
            parsed = urlparse(self.path)
            query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
            body = self._body() if self.command == "POST" else None
            if isinstance(body, ApiError):
                self._json(body.status, {"error": str(body)})
                return
            if parsed.path.startswith("/api/"):
                try:
                    status, payload = handle_api(self.command, parsed.path, query, body, folder)
                except ApiError as exc:
                    self._json(exc.status, {"error": str(exc)})
                    return
                except PlaceError as exc:
                    self._json(400, {"error": str(exc)})
                    return
                self._json(status, payload)
                return
            self._static(parsed.path, static)

        def _body(self) -> dict | None | ApiError:
            length = int(self.headers.get("Content-Length") or "0")
            if length > _MAX_BODY:
                return ApiError(400, "Request body is too large")
            if length <= 0:
                return {}
            try:
                data = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                return ApiError(400, "Request body is not JSON")
            if not isinstance(data, dict):
                return ApiError(400, "Request body must be a JSON object")
            return data

        def _json(self, status: int, payload: dict) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def _static(self, url_path: str, folder: Path | None) -> None:
            if folder is None:
                page = (
                    "<!doctype html><title>PROVE</title>"
                    "<p>PROVE place board API is at <a href=\"/api/places\">/api/places</a>. "
                    "Build the page with <code>npm run build</code> in <code>web/</code>.</p>"
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(page)))
                self.end_headers()
                self.wfile.write(page)
                return
            rel = url_path.lstrip("/") or "index.html"
            target = (folder / rel).resolve()
            base = folder.resolve()
            if not target.is_relative_to(base) or not target.is_file():
                if "." in Path(rel).name:
                    self.send_error(404)
                    return
                target = base / "index.html"
            if not target.is_file():
                self.send_error(404)
                return
            mime = _STATIC_TYPES.get(target.suffix) or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return ThreadingHTTPServer((host, port), Handler)


def handle_api(method: str, path: str, query: dict, body: dict | None, root: Path) -> tuple[int, dict]:
    """One board request. ``body`` is the JSON object for POST."""
    if method == "GET" and path == "/api/places":
        return 200, {"places": list_places(root)}
    if method == "GET" and path == "/api/board":
        place = Place.load(resolve_place(root, query.get("file", "")))
        return 200, place_board(place)
    if method == "GET" and path == "/api/evidence":
        place = Place.load(resolve_place(root, query.get("file", "")))
        intent_id = str(query.get("intent") or "")
        if not intent_id:
            raise PlaceError("Evidence needs an intent id")
        return 200, evidence_view(place, intent_id)
    if method != "POST":
        raise ApiError(404, "No such board route")
    payload = body or {}
    place = Place.load(resolve_place(root, str(payload.get("file") or "")))
    if path == "/api/plan":
        outcome = plan(place)
        return 200, {"ok": True, "code": outcome.code, "lines": outcome.lines, "board": place_board(place)}
    if path == "/api/goal":
        lines = add_goal(
            place,
            statement=str(payload.get("statement") or ""),
            contains=_texts(payload.get("contains")),
            absent=_texts(payload.get("absent")),
            script=_optional(payload.get("script")),
            class_name=str(payload.get("class_name") or "Script"),
            seconds=_number(payload.get("seconds"), default=3),
            name=_optional(payload.get("name")),
            probes=_probes(payload.get("probes")),
            forbid_errors=_flag(payload.get("forbid_errors")),
        )
        place.save()
        return 200, {"ok": True, "lines": lines, "board": place_board(place)}
    if path == "/api/bind":
        lines = bind_claim(
            place,
            str(payload.get("claim") or ""),
            script=_optional(payload.get("script")),
            class_name=str(payload.get("class_name") or "Script"),
            contains=_optional_texts(payload.get("contains")),
            absent=_optional_texts(payload.get("absent")),
            probes=_probes(payload.get("probes")),
            seconds=None if payload.get("seconds") in (None, "") else _number(payload.get("seconds"), default=3),
            forbid_errors=_flag(payload.get("forbid_errors")),
        )
        place.save()
        return 200, {"ok": True, "lines": lines, "board": place_board(place)}
    if path == "/api/answer":
        answer_question(place, str(payload.get("question") or ""), str(payload.get("text") or ""))
        place.save()
        return 200, {"ok": True, "lines": [f"answered {payload.get('question')}"], "board": place_board(place)}
    raise ApiError(404, "No such board route")


def run_ui(host: str = "127.0.0.1", port: int = 8765, *, open_browser: bool = True, root: Path | None = None) -> None:
    """Serve the board until the process is interrupted."""
    folder = root or locate_root(Path(__file__))
    if folder is None:
        raise PlaceError("PROVE root was not found")
    server = make_server(folder, host, port)
    url = f"http://{host}:{server.server_address[1]}/"
    print(f"PROVE board {url}", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _optional(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _texts(value: object) -> list[str]:
    found = _optional_texts(value)
    return found or []


def _optional_texts(value: object) -> list[str] | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        items = [str(item) for item in value if str(item).strip()]
        return items or None
    raise PlaceError("Text list needs strings")


def _probes(value: object) -> list[dict] | None:
    if value is None or value == "" or value == []:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise PlaceError(f"Probe is not JSON: {exc}") from exc
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return value
    raise PlaceError("A probe is a JSON object")


def _number(value: object, *, default: float) -> float:
    if value is None or value == "":
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise PlaceError("Seconds must be a positive number")
    try:
        return float(value)
    except ValueError as exc:
        raise PlaceError("Seconds must be a positive number") from exc


def _flag(value: object) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    raise PlaceError("forbid_errors must be true or false")
