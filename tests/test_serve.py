"""Sidecar server endpoints: live viewer, factor schema, deterministic
re-runs, replication payloads, and error surfaces."""

import http.client
import json
import threading

import pytest

import simulation_engine.serve as serve_mod
from simulation_engine.serve import make_server

MODEL_PY = '''
from simulation_engine import Exponential, Model, Queue, Service, Sink, Source

FACTORS = {"lam": {"min": 0.1, "max": 0.95, "step": 0.05}}


def make_model(lam: float = 0.5, service_time=Exponential(mean=1.0)):
    m = Model("tiny_served", time_unit="minutes")
    src = Source(m, "arrivals", rate=lam)
    q = Queue(m, "queue")
    svc = Service(m, "server", duration=service_time, resource=1)
    snk = Sink(m, "done")
    src >> q
    q >> svc
    svc >> snk
    return m
'''


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    path = tmp_path_factory.mktemp("served") / "model.py"
    path.write_text(MODEL_PY)
    (path.parent / "conceptual-model.md").write_text("# CM\n\nA tiny served queue.")
    httpd = make_server(str(path), port=0, until=200.0, seed=5)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address[:2]
    httpd.shutdown()


def request(server, method, path, body=None):
    conn = http.client.HTTPConnection(*server, timeout=30)
    payload = json.dumps(body) if body is not None else None
    conn.request(method, path, body=payload, headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    return resp.status, raw


def test_root_serves_live_viewer(server):
    status, raw = request(server, "GET", "/")
    html = raw.decode()
    assert status == 200
    assert '"live":true' in html
    assert '"factors":' in html
    assert '"conceptual_model":' in html
    assert "/*__SIM_DATA__*/null" not in html


def test_factor_schema(server):
    status, raw = request(server, "GET", "/api/factors")
    assert status == 200
    data = json.loads(raw)
    by_name = {f["name"]: f for f in data["factors"]}
    assert by_name["lam"]["kind"] == "float" and by_name["lam"]["max"] == 0.95
    assert by_name["service_time"]["kind"] == "distribution"
    assert data["defaults"]["until"] == 200.0
    assert any(d["type"] == "Exponential" for d in data["distributions"])


def test_run_is_deterministic_and_factor_sensitive(server):
    body = {"factors": {"lam": 0.6}, "seed": 9}
    s1, r1 = request(server, "POST", "/api/run", body)
    s2, r2 = request(server, "POST", "/api/run", body)
    assert s1 == s2 == 200
    assert r1 == r2  # identical request -> identical bytes
    kpis = json.loads(r1)["kpis"]
    assert kpis["run"]["seed"] == 9

    # A different service distribution must change the outcome.
    s3, r3 = request(server, "POST", "/api/run", {
        "factors": {"lam": 0.6, "service_time": {"type": "Constant", "args": {"value": 0.1}}},
        "seed": 9,
    })
    assert s3 == 200
    k3 = json.loads(r3)["kpis"]
    assert k3["blocks"]["done"]["time_in_system"]["mean"] < \
        kpis["blocks"]["done"]["time_in_system"]["mean"]


def test_replicate_returns_samples_and_percentiles(server):
    status, raw = request(server, "POST", "/api/replicate", {"factors": {}, "n": 5, "seed": 3})
    assert status == 200
    data = json.loads(raw)
    assert data["n"] == 5
    assert len(data["kpi_samples"]["done.count"]) == 5
    assert set(data["percentiles"]["done.count"]) == {"p5", "p10", "p50", "p90", "p95"}
    assert data["kpi_table"]["done.count"]["ci_low"] <= data["kpi_table"]["done.count"]["mean"]


def test_error_surfaces(server):
    status, raw = request(server, "POST", "/api/replicate", {"factors": {"ghost": 1}, "n": 5})
    assert status == 400 and "unknown factor" in json.loads(raw)["error"]

    status, raw = request(server, "POST", "/api/replicate", {"n": 1})
    assert status == 400 and "n must be" in json.loads(raw)["error"]

    status, raw = request(server, "POST", "/api/run", {"factors": {"lam": -2}})
    assert status in (400, 500)  # ctor/validation error, surfaced as a message
    assert "error" in json.loads(raw)

    status, _ = request(server, "GET", "/nope")
    assert status == 404


def test_trace_cap_maps_to_413(server, monkeypatch):
    monkeypatch.setattr(serve_mod, "MAX_TRACE_EVENTS", 10)
    status, raw = request(server, "POST", "/api/run", {"factors": {}})
    assert status == 413
    assert "events" in json.loads(raw)["error"]
