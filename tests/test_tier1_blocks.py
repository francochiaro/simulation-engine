import pytest

from simulation_engine import (
    Batch,
    Constant,
    Exponential,
    Fleet,
    Gate,
    Model,
    ResourcePool,
    Ride,
    Service,
    Sink,
    Source,
    TimeMeasureEnd,
    TimeMeasureStart,
    Triangular,
    Unbatch,
)


def test_batch_unbatch_preserves_entity_balance():
    m = Model("batching")
    src = Source(m, "src", rate=1.0, max_arrivals=40)
    b = Batch(m, "cart", size=4)
    u = Unbatch(m, "uncart")
    snk = Sink(m, "done")
    src >> b
    b >> u
    u >> snk
    res = m.run(until=200, seed=1)
    ent = res.kpis["entities"]
    assert ent["balance_ok"]
    # 40 members + 10 containers, all disposed.
    assert res.kpis["blocks"]["done"]["count"] == 40
    assert ent["disposed"] == 50


def test_batch_timeout_emits_partial():
    m = Model("partial")
    src = Source(m, "src", arrival_times=[0, 1, 2])  # never reaches size 10
    b = Batch(m, "cart", size=10, timeout=5.0)
    u = Unbatch(m, "uncart")
    snk = Sink(m, "done")
    src >> b
    b >> u
    u >> snk
    res = m.run(until=100, seed=1)
    assert res.kpis["blocks"]["done"]["count"] == 3
    assert res.kpis["entities"]["balance_ok"]


def test_batch_disposed_at_sink_disposes_members():
    m = Model("ship_whole_batch")
    src = Source(m, "src", rate=1.0, max_arrivals=8)
    b = Batch(m, "pallet", size=4)
    snk = Sink(m, "shipped")
    src >> b
    b >> snk  # containers shipped whole, members inside
    res = m.run(until=100, seed=1)
    assert res.kpis["entities"]["balance_ok"]
    assert res.kpis["blocks"]["shipped"]["count"] == 10  # 8 members + 2 pallets


def test_closed_gate_holds_everything():
    m = Model("sealed")
    src = Source(m, "src", rate=10.0)
    g = Gate(m, "gate", initially_open=False)  # never opens
    snk = Sink(m, "done")
    src >> g
    g >> snk
    res = m.run(until=50, seed=2)
    assert res.kpis["blocks"]["done"]["count"] == 0
    assert res.kpis["entities"]["in_system_at_end"] == res.kpis["entities"]["created"]


def test_gate_cycle_delays_and_bursts():
    # A gate conserves flow — it delays arrivals during closed windows and
    # releases them in bursts, so WIP peaks near closed_for × arrival rate.
    m = Model("gated")
    src = Source(m, "src", rate=10.0)
    g = Gate(m, "gate", initially_open=False, cycle=(1.0, 9.0))
    svc = Service(m, "svc", duration=Constant(0.01), resource=100)
    snk = Sink(m, "done")
    src >> g
    g >> svc
    svc >> snk
    res = m.run(until=100, seed=2)
    ent = res.kpis["entities"]
    assert ent["balance_ok"]
    assert ent["wip_max"] > 50           # ~90 pile up behind each closure
    assert res.kpis["blocks"]["done"]["count"] > 800  # flow is conserved


def test_time_measure_pair():
    m = Model("measured")
    src = Source(m, "src", rate=1.0, max_arrivals=20)
    t0 = TimeMeasureStart(m, "t0", measure="span")
    svc = Service(m, "svc", duration=Constant(2.0), resource=20)
    t1 = TimeMeasureEnd(m, "t1", measure="span")
    snk = Sink(m, "done")
    src >> t0
    t0 >> svc
    svc >> t1
    t1 >> snk
    res = m.run(until=100, seed=3)
    el = res.kpis["blocks"]["t1"]["elapsed"]
    assert el["n"] == 20
    assert el["mean"] == pytest.approx(2.0)


def test_pool_downtime_reduces_availability():
    m = Model("flaky")
    pool = ResourcePool(
        m, "machine", capacity=1,
        mtbf=Exponential(mean=50.0), mttr=Triangular(5, 10, 20),
    )
    src = Source(m, "src", rate=0.05)
    svc = Service(m, "svc", duration=Constant(1.0), resource=pool)
    snk = Sink(m, "done")
    src >> svc
    svc >> snk
    res = m.run(until=5000, seed=4)
    p = res.kpis["pools"]["machine"]
    assert 0.6 < p["availability"] < 0.95
    # Productive utilization excludes downtime.
    assert p["utilization"] < p["busy"]["mean"] / p["capacity"]


def test_ride_moves_entities_and_tracks_positions():
    m = Model("lift", time_unit="seconds")
    fleet = Fleet(m, "car", n_cars=1, speed=1.0, load_time=1.0, unload_time=1.0)
    src = Source(m, "src", arrival_times=[0.0, 5.0])
    ride = Ride(m, "ride", fleet=fleet, from_pos=0.0, to_pos=10.0)
    snk = Sink(m, "done")
    src >> ride
    ride >> snk
    res = m.run(until=100, seed=5)
    assert res.kpis["blocks"]["done"]["count"] == 2
    # Second rider waits for the car's return deadhead: trip = 1+10+1 = 12s,
    # deadhead back 10s. First done at 12, second starts ~17 (arrived 5,
    # car free at 12, deadhead 10 → moves 22..32 +load/unload.
    tis = res.kpis["blocks"]["done"]["time_in_system"]
    assert tis["max"] > tis["min"]  # the queueing rider waited longer
    moves = [r for r in res.trace.records if r["event"] == "move"]
    assert any(r.get("note") == "deadhead" for r in moves)
    assert all("t_end" in r for r in moves)
