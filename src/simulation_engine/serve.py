"""Local sidecar server: the interactive counterpart of the static viewer.

    uv run python -m simulation_engine.serve path/to/model.py [--port 8000]
        [--host 127.0.0.1] [--until X] [--warmup X] [--seed N]

The target file must define ``make_model(**factors)`` (the same contract the
/simulate skill and ``sweep()`` use) and may define a ``FACTORS`` metadata
dict and a ``HORIZON`` constant (the natural run length in model time units —
used when ``--until`` is not given; models whose sources never stop need one
or the other). The server runs one baseline showcase at the default factors,
serves the viewer at ``/`` in live mode, and re-runs the engine on demand:

- ``GET  /``              the viewer HTML (controls active)
- ``GET  /api/factors``   factor schema + editable-distribution catalog
- ``POST /api/run``       one showcase run -> {model, trace, kpis}
- ``POST /api/replicate`` N replications  -> {kpi_table, kpi_samples, percentiles}

Same engine, same numbers as the CLI: ``/api/run`` is deterministic in
(factors, until, seed, replication), and ``/api/replicate`` varies
``replication`` per rep exactly like ``experiments.replicate``.

Implementation notes: pure stdlib (ThreadingHTTPServer); simulation work is
serialized behind one lock (single local user — the page disables its Run
buttons while a request is in flight); replications always run with
``n_workers=1`` because a spec-loaded user module does not pickle reliably
for ProcessPoolExecutor.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .experiments import replicate
from .factors import coerce_factors, describe_factors, distribution_catalog
from .model import ModelValidationError, sanitize_json
from .viewer.build_viewer import MAX_TRACE_EVENTS, _json_default, _render

REPLICATION_CAP = 1000


def load_model_module(path: str):
    """Import the user's model.py; returns (make_model, FACTORS, HORIZON)."""
    path = os.path.abspath(path)
    spec = importlib.util.spec_from_file_location("_sim_user_model", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_sim_user_model"] = mod
    spec.loader.exec_module(mod)  # __name__ != "__main__": showcase blocks don't fire
    factory = getattr(mod, "make_model", None)
    if not callable(factory):
        raise SystemExit(f"{path} must define make_model(**factors)")
    horizon = getattr(mod, "HORIZON", None)
    if horizon is not None:
        horizon = float(horizon)
    return factory, getattr(mod, "FACTORS", None), horizon


def find_conceptual_model(model_path: str) -> str | None:
    for name in ("conceptual-model.md", "conceptual_model.md"):
        p = os.path.join(os.path.dirname(os.path.abspath(model_path)), name)
        if os.path.exists(p):
            with open(p) as f:
                return f.read()
    return None


class SimServer:
    def __init__(self, factory, schema, *, until, warmup, seed, conceptual_model=None):
        self.factory = factory
        self.schema = schema
        self.until = until
        self.warmup = warmup
        self.seed = seed
        self.conceptual_model = conceptual_model
        self.lock = threading.Lock()  # one simulation at a time
        self.baseline_html: str | None = None

    def defaults(self) -> dict:
        return {"until": self.until, "warmup": self.warmup, "seed": self.seed}

    def factors_payload(self) -> dict:
        return {
            "factors": self.schema,
            "distributions": distribution_catalog(),
            "defaults": self.defaults(),
        }

    def build_baseline(self) -> None:
        with self.lock:
            rr = self.factory().run(until=self.until, seed=self.seed, warmup=self.warmup)
        if self.until is None:
            # Bounded-source model: echo the observed horizon to the UI.
            self.until = rr.kpis["run"]["t_end"]
        self.baseline_html = _render(
            rr.model_json,
            rr.trace.records,
            rr.kpis,
            None,
            extra={
                "live": True,
                "factors": self.schema,
                "dist_catalog": distribution_catalog(),
                "defaults": self.defaults(),
                "conceptual_model": self.conceptual_model,
            },
        )

    def run_once(self, body: dict) -> dict:
        params = coerce_factors(body.get("factors") or {}, self.schema)
        until = body.get("until", self.until)
        seed = int(body.get("seed", self.seed))
        warmup = float(body.get("warmup", self.warmup))
        replication = int(body.get("replication", 0))
        with self.lock:
            rr = self.factory(**params).run(
                until=until, seed=seed, warmup=warmup, replication=replication
            )
        if len(rr.trace.records) > MAX_TRACE_EVENTS:
            raise TraceTooLarge(
                f"Trace has {len(rr.trace.records):,} events (> {MAX_TRACE_EVENTS:,}) — "
                f"use a smaller until= for the animated run"
            )
        return {"model": rr.model_json, "trace": rr.trace.records, "kpis": rr.kpis}

    def run_replications(self, body: dict) -> dict:
        params = coerce_factors(body.get("factors") or {}, self.schema)
        n = body.get("n")
        if not isinstance(n, int) or isinstance(n, bool) or n < 2 or n > REPLICATION_CAP:
            raise ValueError(f"n must be an integer in [2, {REPLICATION_CAP}], got {n!r}")
        until = body.get("until", self.until)
        seed = int(body.get("seed", self.seed))
        warmup = float(body.get("warmup", self.warmup))
        confidence = float(body.get("confidence", 0.95))
        with self.lock:
            reps = replicate(
                self.factory,
                n=n,
                params=params,
                until=until,
                warmup=warmup,
                seed=seed,
                confidence=confidence,
                keep_showcase=False,
            )
        return {
            "n": reps.n,
            "confidence": reps.confidence,
            "kpi_table": reps.table(),
            "kpi_samples": reps.kpi_samples,
            "percentiles": {k: reps.percentiles(k) for k in sorted(reps.kpi_samples)},
        }


class TraceTooLarge(Exception):
    pass


def make_handler(sim: SimServer):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quiet
            pass

        def _send(self, status: int, content: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def _send_json(self, status: int, obj) -> None:
            data = json.dumps(sanitize_json(obj), default=_json_default).encode()
            self._send(status, data, "application/json")

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/":
                assert sim.baseline_html is not None
                self._send(200, sim.baseline_html.encode(), "text/html; charset=utf-8")
            elif path == "/api/factors":
                self._send_json(200, sim.factors_payload())
            else:
                self._send_json(404, {"error": f"no such path: {path}"})

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError("request body must be a JSON object")
            except (ValueError, json.JSONDecodeError) as e:
                self._send_json(400, {"error": f"bad request body: {e}"})
                return
            try:
                if path == "/api/run":
                    self._send_json(200, sim.run_once(body))
                elif path == "/api/replicate":
                    self._send_json(200, sim.run_replications(body))
                else:
                    self._send_json(404, {"error": f"no such path: {path}"})
            except TraceTooLarge as e:
                self._send_json(413, {"error": str(e)})
            except ModelValidationError as e:
                self._send_json(400, {"error": str(e)})
            except (ValueError, TypeError) as e:
                self._send_json(400, {"error": str(e)})
            except Exception as e:  # noqa: BLE001 — surface anything else as 500
                self._send_json(500, {"error": f"{type(e).__name__}: {e}"})

    return Handler


def make_server(model_path: str, *, host="127.0.0.1", port=0, until=None,
                warmup=0.0, seed=12345) -> ThreadingHTTPServer:
    """Build a ready-to-serve HTTP server (baseline already run). Split from
    main() so tests can start it on port 0 in a thread."""
    factory, factors_meta, horizon = load_model_module(model_path)
    schema = describe_factors(factory, factors_meta)
    sim = SimServer(
        factory, schema, until=until if until is not None else horizon,
        warmup=warmup, seed=seed,
        conceptual_model=find_conceptual_model(model_path),
    )
    try:
        sim.build_baseline()
    except ModelValidationError as e:
        if "No run length" in str(e) and until is None:
            raise SystemExit(
                f"{e}\nThis model has no natural end — pass --until <horizon> "
                f"or declare HORIZON = <horizon> in the model file."
            ) from e
        raise
    return ThreadingHTTPServer((host, port), make_handler(sim))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(
        prog="python -m simulation_engine.serve",
        description="Serve a model.py as an interactive viewer.",
    )
    ap.add_argument("model", help="path to a model.py defining make_model(**factors)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--until", type=float, default=None, help="showcase horizon (model time units)")
    ap.add_argument("--warmup", type=float, default=0.0)
    ap.add_argument("--seed", type=int, default=12345)
    args = ap.parse_args(argv)

    httpd = make_server(
        args.model, host=args.host, port=args.port,
        until=args.until, warmup=args.warmup, seed=args.seed,
    )
    host, port = httpd.server_address[:2]
    print(f"Serving {os.path.abspath(args.model)} at http://{host}:{port}  (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
