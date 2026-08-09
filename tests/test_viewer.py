import json

import pytest

from simulation_engine import Exponential, Model, Queue, Service, Sink, Source
from simulation_engine.viewer import build_viewer as bv


def small_run():
    m = Model("tiny", time_unit="minutes")
    src = Source(m, "src", rate=1.0, max_arrivals=20)
    q = Queue(m, "q")
    svc = Service(m, "svc", duration=Exponential(mean=0.8), resource=1)
    snk = Sink(m, "done")
    src >> q
    q >> svc
    svc >> snk
    return m.run(until=100, seed=2)


def test_build_viewer_inlines_everything(tmp_path):
    res = small_run()
    path = bv.build_viewer(res, out_dir=str(tmp_path))
    html = open(path).read()
    assert "/*__SIM_DATA__*/null" not in html
    assert "__TITLE__" not in html
    assert '"model":' in html and '"trace":' in html and '"kpis":' in html
    # The three artifacts also exist standalone, as strict JSON.
    json.load(open(tmp_path / "model.json"))
    json.load(open(tmp_path / "kpis.json"))
    with open(tmp_path / "trace.jsonl") as f:
        for line in f:
            json.loads(line)


def test_build_from_dir_roundtrip(tmp_path):
    res = small_run()
    bv.build_viewer(res, out_dir=str(tmp_path))
    (tmp_path / "index.html").unlink()
    path = bv.build_from_dir(str(tmp_path))
    assert path.endswith("index.html")
    assert '"model":' in open(path).read()


def test_trace_size_guard(tmp_path, monkeypatch):
    res = small_run()
    monkeypatch.setattr(bv, "MAX_TRACE_EVENTS", 10)
    with pytest.raises(ValueError, match="animate a shorter run"):
        bv.build_viewer(res, out_dir=str(tmp_path))


def test_experiment_payload_and_extras_embed_and_roundtrip(tmp_path):
    from simulation_engine.experiments import replicate
    from simulation_engine.factors import describe_factors

    def factory():
        m = Model("tiny", time_unit="minutes")
        src = Source(m, "src", rate=1.0, max_arrivals=20)
        svc = Service(m, "svc", duration=Exponential(mean=0.8), resource=1)
        snk = Sink(m, "done")
        src >> svc
        svc >> snk
        return m

    reps = replicate(factory, n=3, until=100, seed=2, keep_showcase=True)
    assert reps.showcase is not None
    payload = reps.as_payload()
    assert payload["n_replications"] == 3
    assert len(payload["kpi_samples"]["done.count"]) == 3
    assert set(payload["percentiles"]["done.count"]) == {"p5", "p10", "p50", "p90", "p95"}

    schema = describe_factors(factory)
    path = bv.build_viewer(
        reps.showcase,
        out_dir=str(tmp_path),
        experiment={"kind": "replications", **payload},
        conceptual_model="# Conceptual model\n\nA tiny queue.",
        factors=schema,
    )
    html = open(path).read()
    assert '"kpi_samples":' in html
    assert '"conceptual_model":' in html
    assert '"factors":' in html
    # experiment.json now round-trips through build_from_dir, and the
    # conceptual model survives via conceptual_model.md.
    exp = json.load(open(tmp_path / "experiment.json"))
    assert exp["n_replications"] == 3
    assert (tmp_path / "conceptual_model.md").exists()
    (tmp_path / "index.html").unlink()
    rebuilt = open(bv.build_from_dir(str(tmp_path))).read()
    assert '"kpi_samples":' in rebuilt
    assert '"conceptual_model":' in rebuilt
