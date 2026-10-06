"""The HTML tool: a stdlib HTTP server with a small JSON API.

No web framework on purpose - ``python run.py`` has to work on a locked-down
work machine with nothing but Python and numpy installed.

    GET  /                       the single-page UI
    GET  /api/bootstrap          asset classes, benchmarks, saved scenarios
    POST /api/simulate           {scenarios: [...], start, end}  -> metrics
    POST /api/frontier           {bounds, start, end, points}    -> bullet
    POST /api/scenario           save a scenario
    DELETE /api/scenario?name=   delete a scenario
"""

from __future__ import annotations

import json
import math
import mimetypes
import threading
import traceback
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np

from . import frontier as frontier_mod
from . import metrics
from .data import ROOT, asset_classes, panel, reset_caches
from .portfolio import Scenario, align, simulate
from .store import ScenarioStore

STATIC_DIR = ROOT / "static"
TEMPLATE_DIR = ROOT / "templates"

MAX_BODY_BYTES = 2_000_000
_frontier_cache: dict[str, dict] = {}
_frontier_lock = threading.Lock()


def jsonable(value):
    """Make numpy scalars and non-finite floats safe for ``json.dumps``.

    numpy bools and float64s are not JSON types, and NaN/Infinity are not valid
    JSON, so they become ``null`` and the client renders an en dash.
    """
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return [jsonable(v) for v in value.tolist()]
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (float, np.floating)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, np.generic):
        return jsonable(value.item())
    return value


# --------------------------------------------------------------------------- #
# payload builders
# --------------------------------------------------------------------------- #
def bootstrap_payload() -> dict:
    classes, risk_free = asset_classes()
    data = panel()
    store = ScenarioStore()

    return {
        "asset_classes": [
            {
                **asdict(cls),
                "alternatives": list(cls.alternatives),
                "choices": [
                    {
                        "ticker": ticker,
                        "label": data.describe(ticker).get("description") or ticker,
                        "first_month": data.describe(ticker).get("first_month"),
                        "last_month": data.describe(ticker).get("last_month"),
                        "currency": data.describe(ticker).get("currency"),
                    }
                    for ticker in cls.benchmark_choices()
                    if data.has(ticker)
                ],
            }
            for cls in classes
        ],
        "risk_free": {
            "ticker": risk_free,
            "label": data.describe(risk_free).get("description") or risk_free,
        },
        "benchmarks": [
            {
                "ticker": ticker,
                **{
                    key: data.describe(ticker).get(key)
                    for key in ("description", "currency", "first_month", "last_month", "months")
                },
            }
            for ticker in sorted(data.tickers)
        ],
        "months": {"first": data.months[0], "last": data.months[-1]},
        "scenarios": [s.to_dict() for s in store.list()],
    }


def simulate_payload(body: dict) -> dict:
    classes, risk_free = asset_classes()
    data = panel()
    start = body.get("start") or None
    end = body.get("end") or None
    common = bool(body.get("common_window", True))

    scenarios = [Scenario.from_dict(raw) for raw in body.get("scenarios", [])]
    if not scenarios:
        return {"error": "Kein Szenario übergeben.", "results": []}

    sims = [
        simulate(
            scenario,
            data,
            list(classes),
            risk_free_ticker=risk_free,
            start=start,
            end=end,
        )
        for scenario in scenarios
    ]

    results = [sim.to_dict() for sim in sims]

    # A fair side-by-side needs one shared window; report it separately so the
    # per-scenario figures over their own full history stay visible too.
    comparison = None
    usable = [s for s in sims if s.months]
    if len(usable) > 1:
        months, series = align(usable)
        if months:
            rf_index = {m: i for i, m in enumerate(usable[0].months)}
            rf = np.asarray(
                [usable[0].risk_free[rf_index[m]] for m in months], dtype=float
            )
            comparison = {
                "months": months,
                "scenarios": [
                    {
                        "name": name,
                        "stats": metrics.summarise(returns, months, rf).to_dict(),
                        "wealth": [float(x) for x in metrics.wealth_curve(returns)],
                        "drawdown": [float(x) for x in metrics.drawdown_series(returns)],
                        "calendar_years": metrics.calendar_years(returns, months),
                    }
                    for name, returns in series.items()
                ],
            }

    correlation = None
    if usable:
        reference = usable[0]
        if reference.asset_returns.size:
            correlation = {
                "asset_classes": reference.members,
                "matrix": [
                    [None if np.isnan(v) else float(v) for v in row]
                    for row in reference.correlation()
                ],
            }

    return {"error": None, "results": results, "comparison": comparison, "correlation": correlation}


def frontier_payload(body: dict) -> dict:
    classes, risk_free = asset_classes()
    data = panel()

    selected = body.get("asset_classes") or [c.name for c in classes]
    by_name = {c.name: c for c in classes}
    overrides = body.get("benchmarks") or {}

    names: list[str] = []
    tickers: list[str] = []
    for name in selected:
        if name not in by_name:
            continue
        ticker = overrides.get(name) or by_name[name].benchmark
        if data.has(ticker):
            names.append(name)
            tickers.append(ticker)

    if len(names) < 2:
        return {"error": "Mindestens zwei Assetklassen mit Zeitreihe nötig.", "points": []}

    start = body.get("start") or None
    end = body.get("end") or None
    bounds_raw = body.get("bounds") or {}
    points = int(body.get("points") or 36)
    points = max(6, min(points, 80))

    key = json.dumps(
        {"t": tickers, "n": names, "s": start, "e": end, "b": bounds_raw, "p": points},
        sort_keys=True,
    )
    with _frontier_lock:
        if key in _frontier_cache:
            return _frontier_cache[key]

    matrix = data.matrix(tickers)
    usable = ~np.isnan(matrix).any(axis=1)
    months = np.asarray(data.months)
    if start:
        usable &= months >= start
    if end:
        usable &= months <= end

    rows = np.flatnonzero(usable)
    if rows.size < 3:
        return {
            "error": "Zu wenige gemeinsame Monate für eine Effizienzlinie.",
            "points": [],
        }

    bounds = {}
    for name in names:
        entry = bounds_raw.get(name)
        if not entry:
            continue
        low = float(entry.get("min", 0.0) or 0.0)
        high = float(entry.get("max", 1.0) if entry.get("max") is not None else 1.0)
        bounds[name] = (max(0.0, low), max(low, min(1.0, high)))

    rf_column = data.column(risk_free)[rows] if data.has(risk_free) else None
    rf = None if rf_column is None else np.nan_to_num(rf_column, nan=0.0)

    result = frontier_mod.efficient_frontier(
        matrix[rows, :], names, points=points, bounds=bounds, risk_free=rf
    )
    result["window"] = {
        "start": data.months[int(rows[0])],
        "end": data.months[int(rows[-1])],
        "months": int(rows.size),
    }
    result["proxy_classes"] = [n for n in names if by_name[n].proxy]

    with _frontier_lock:
        if len(_frontier_cache) > 64:
            _frontier_cache.clear()
        _frontier_cache[key] = result
    return result


# --------------------------------------------------------------------------- #
# HTTP plumbing
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    server_version = "SAA-Tool/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:  # quieter console
        if "/api/" in (self.path or ""):
            super().log_message(fmt, *args)

    # -- helpers --
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(
            jsonable(payload), allow_nan=False, ensure_ascii=False
        ).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > MAX_BODY_BYTES:
            raise ValueError("Request-Body zu groß.")
        raw = self.rfile.read(length)
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("JSON-Objekt erwartet.")
        return parsed

    def _serve_file(self, path: Path, fallback_type: str = "text/plain") -> None:
        if not path.is_file():
            self._json({"error": f"nicht gefunden: {path.name}"}, 404)
            return
        guessed = mimetypes.guess_type(path.name)[0] or fallback_type
        charset = "; charset=utf-8" if guessed.startswith("text/") or "javascript" in guessed else ""
        self._send(200, path.read_bytes(), f"{guessed}{charset}")

    # -- routes --
    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path)
        try:
            if route.path in ("/", "/index.html"):
                self._serve_file(TEMPLATE_DIR / "index.html", "text/html")
            elif route.path == "/api/bootstrap":
                reset_caches()
                self._json(bootstrap_payload())
            elif route.path == "/api/health":
                self._json({"ok": True})
            elif route.path.startswith("/static/"):
                name = route.path[len("/static/") :]
                target = (STATIC_DIR / name).resolve()
                if not str(target).startswith(str(STATIC_DIR.resolve())):
                    self._json({"error": "ungültiger Pfad"}, 403)
                    return
                self._serve_file(target)
            else:
                self._json({"error": "unbekannte Route"}, 404)
        except Exception as exc:  # pragma: no cover - surfaced to the browser
            traceback.print_exc()
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path)
        try:
            body = self._read_json()
            if route.path == "/api/simulate":
                self._json(simulate_payload(body))
            elif route.path == "/api/frontier":
                self._json(frontier_payload(body))
            elif route.path == "/api/scenario":
                scenario = Scenario.from_dict(body)
                path = ScenarioStore().save(scenario)
                self._json({"saved": scenario.name, "file": path.name})
            else:
                self._json({"error": "unbekannte Route"}, 404)
        except (ValueError, KeyError) as exc:
            self._json({"error": str(exc)}, 400)
        except Exception as exc:  # pragma: no cover
            traceback.print_exc()
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    def do_DELETE(self) -> None:  # noqa: N802
        route = urlparse(self.path)
        if route.path != "/api/scenario":
            self._json({"error": "unbekannte Route"}, 404)
            return
        name = (parse_qs(route.query).get("name") or [""])[0]
        if not name:
            self._json({"error": "Parameter 'name' fehlt."}, 400)
            return
        self._json({"deleted": ScenarioStore().delete(name), "name": name})


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"SAA-Tool laeuft auf http://{host}:{port}/  (Strg+C beendet)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbeendet")
    finally:
        httpd.server_close()
