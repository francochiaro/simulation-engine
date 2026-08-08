"""Build a self-contained replay viewer.

The viewer is one HTML file with the run's three artifacts (model graph,
event trace, KPIs) inlined — because ``file://`` pages cannot fetch sibling
files, inlining is what makes the result double-clickable and shareable.

Usage:
    from simulation_engine.viewer.build_viewer import build_viewer
    path = build_viewer(run_result, out_dir="runs/2026-08-08")

    # or from artifacts already on disk:
    python -m simulation_engine.viewer.build_viewer <run_dir>
"""

from __future__ import annotations

import json
import math
import os
import sys
from importlib import resources

MAX_TRACE_EVENTS = 200_000  # keep the HTML tractable; animate a shorter run if hit


def _json_default(o):
    if isinstance(o, float) and math.isnan(o):
        return None
    raise TypeError(f"not JSON serializable: {type(o)}")


def _render(model: dict, trace_records: list, kpis: dict, experiment: dict | None) -> str:
    template = (
        resources.files("simulation_engine.viewer").joinpath("template.html").read_text()
    )
    if len(trace_records) > MAX_TRACE_EVENTS:
        raise ValueError(
            f"Trace has {len(trace_records):,} events (> {MAX_TRACE_EVENTS:,}) — "
            f"animate a shorter run (smaller until=) and keep long runs for "
            f"statistics with trace_level='off'"
        )
    from ..model import sanitize_json

    payload = json.dumps(
        sanitize_json(
            {"model": model, "trace": trace_records, "kpis": kpis, "experiment": experiment}
        ),
        separators=(",", ":"),
        default=_json_default,
    ).replace("</", "<\\/")
    title = f"{model.get('name', 'simulation')} — simulation"
    return template.replace("__TITLE__", title).replace("/*__SIM_DATA__*/null", payload)


def build_viewer(run_result, out_dir: str, experiment: dict | None = None) -> str:
    """Write the run artifacts + index.html into ``out_dir``; returns the
    absolute path of the viewer HTML."""
    run_result.to_files(out_dir)
    html = _render(
        run_result.model_json, run_result.trace.records, run_result.kpis, experiment
    )
    path = os.path.abspath(os.path.join(out_dir, "index.html"))
    with open(path, "w") as f:
        f.write(html)
    return path


def build_from_dir(run_dir: str) -> str:
    """Rebuild index.html from model.json + trace.jsonl + kpis.json on disk."""
    with open(os.path.join(run_dir, "model.json")) as f:
        model = json.load(f)
    with open(os.path.join(run_dir, "kpis.json")) as f:
        kpis = json.load(f)
    records = []
    with open(os.path.join(run_dir, "trace.jsonl")) as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    exp_path = os.path.join(run_dir, "experiment.json")
    experiment = None
    if os.path.exists(exp_path):
        with open(exp_path) as f:
            experiment = json.load(f)
    html = _render(model, records, kpis, experiment)
    path = os.path.abspath(os.path.join(run_dir, "index.html"))
    with open(path, "w") as f:
        f.write(html)
    return path


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m simulation_engine.viewer.build_viewer <run_dir>")
    print(build_from_dir(sys.argv[1]))
