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


def _render(
    model: dict,
    trace_records: list,
    kpis: dict,
    experiment: dict | None,
    extra: dict | None = None,
) -> str:
    """Inline the payload into the template. ``extra`` merges additional
    top-level SIM keys — ``conceptual_model`` (markdown string), ``factors``
    (schema list), and the sidecar server's ``live``/``dist_catalog``/
    ``defaults``. Absent keys stay absent: the JS null-guards everything."""
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

    sim = {"model": model, "trace": trace_records, "kpis": kpis, "experiment": experiment}
    for k, v in (extra or {}).items():
        if v is not None:
            sim[k] = v
    payload = json.dumps(
        sanitize_json(sim),
        separators=(",", ":"),
        default=_json_default,
    ).replace("</", "<\\/")
    title = f"{model.get('name', 'simulation')} — simulation"
    return template.replace("__TITLE__", title).replace("/*__SIM_DATA__*/null", payload)


def build_viewer(
    run_result,
    out_dir: str,
    experiment: dict | None = None,
    *,
    conceptual_model: str | None = None,
    factors: list | None = None,
) -> str:
    """Write the run artifacts + index.html into ``out_dir``; returns the
    absolute path of the viewer HTML.

    ``conceptual_model`` is the conceptual-model.md markdown (rendered in the
    viewer's Model tab); ``factors`` is a ``describe_factors()`` schema
    (displayed read-only — the static viewer cannot re-run)."""
    run_result.to_files(out_dir)
    from ..model import sanitize_json

    if experiment is not None:
        with open(os.path.join(out_dir, "experiment.json"), "w") as f:
            json.dump(sanitize_json(experiment), f, default=_json_default)
    if conceptual_model is not None:
        with open(os.path.join(out_dir, "conceptual_model.md"), "w") as f:
            f.write(conceptual_model)
    html = _render(
        run_result.model_json,
        run_result.trace.records,
        run_result.kpis,
        experiment,
        extra={"conceptual_model": conceptual_model, "factors": factors},
    )
    path = os.path.abspath(os.path.join(out_dir, "index.html"))
    with open(path, "w") as f:
        f.write(html)
    return path


def build_from_dir(run_dir: str) -> str:
    """Rebuild index.html from model.json + trace.jsonl + kpis.json on disk
    (plus experiment.json and conceptual_model.md when present)."""
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
    cm_path = os.path.join(run_dir, "conceptual_model.md")
    conceptual_model = None
    if os.path.exists(cm_path):
        with open(cm_path) as f:
            conceptual_model = f.read()
    html = _render(
        model, records, kpis, experiment, extra={"conceptual_model": conceptual_model}
    )
    path = os.path.abspath(os.path.join(run_dir, "index.html"))
    with open(path, "w") as f:
        f.write(html)
    return path


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m simulation_engine.viewer.build_viewer <run_dir>")
    print(build_from_dir(sys.argv[1]))
