import pytest

from simulation_engine import (
    Exponential,
    Model,
    ModelValidationError,
    Queue,
    Release,
    ResourcePool,
    Route,
    Seize,
    Service,
    Sink,
    Source,
)


def mm1(lam=0.8, mu=1.0):
    m = Model("mm1", time_unit="minutes")
    src = Source(m, "arrivals", rate=lam)
    q = Queue(m, "queue")
    svc = Service(m, "server", duration=Exponential(rate=mu), resource=1)
    snk = Sink(m, "done")
    src >> q
    q >> svc
    svc >> snk
    return m


# ---- validation catches each seeded defect ---------------------------------

def test_no_source_is_an_error():
    m = Model("empty")
    Sink(m, "done")
    with pytest.raises(ModelValidationError, match="no Source"):
        m.run(until=10)


def test_unconnected_out_port_is_an_error():
    m = Model("dangling")
    Source(m, "src", rate=1.0, max_arrivals=5)
    with pytest.raises(ModelValidationError, match="unconnected"):
        m.run(until=10)


def test_unbounded_source_without_until_is_an_error():
    m = mm1()
    with pytest.raises(ModelValidationError, match="never stop"):
        m.run()


def test_seize_without_release_is_an_error():
    m = Model("leak")
    pool = ResourcePool(m, "forklifts", capacity=1)
    src = Source(m, "src", rate=1.0)
    s = Seize(m, "grab", resource=pool)
    snk = Sink(m, "done")
    src >> s
    s >> snk
    with pytest.raises(ModelValidationError, match="no reachable Release"):
        m.run(until=10)


def test_route_condition_needs_default():
    m = Model("routes")
    src = Source(m, "src", rate=1.0)
    r = Route(m, "split")
    snk = Sink(m, "done")
    src >> r
    r.add(snk, when=lambda e: True)
    with pytest.raises(ModelValidationError, match="default branch"):
        m.run(until=10)


def test_duplicate_names_rejected():
    m = Model("dupe")
    Source(m, "x", rate=1.0)
    with pytest.raises(ValueError, match="Duplicate"):
        Sink(m, "x")


def test_unreachable_block_is_a_warning_not_error():
    m = mm1()
    Sink(m, "orphan")
    issues = m.validate(until=100)
    assert ("warning", "Block 'orphan' is unreachable from any Source") in issues


# ---- runtime semantics -------------------------------------------------------

def test_seize_release_span_works():
    m = Model("span")
    pool = ResourcePool(m, "cart", capacity=2)
    src = Source(m, "src", rate=0.5)
    s = Seize(m, "take", resource=pool)
    d = Service(m, "aisle", duration=Exponential(mean=1.0), resource=4)
    r = Release(m, "give_back", resource=pool)
    snk = Sink(m, "done")
    src >> s
    s >> d
    d >> r
    r >> snk
    res = m.run(until=500, seed=3)
    assert res.kpis["entities"]["balance_ok"]
    assert res.kpis["pools"]["cart"]["utilization"] > 0


def test_sink_refuses_leaked_tokens():
    # A Release exists and is statically reachable — but a routing bug sends
    # every entity around it. The static validator can't see that; the Sink's
    # runtime guard must.
    m = Model("leaky_runtime")
    pool = ResourcePool(m, "cart", capacity=5)
    src = Source(m, "src", rate=0.5, max_arrivals=3)
    s = Seize(m, "take", resource=pool)
    fork = Route(m, "fork")
    r = Release(m, "give_back", resource=pool)
    snk = Sink(m, "done")
    src >> s
    s >> fork
    fork.add(r, when=lambda e: False)  # the bug: nobody ever releases
    fork.add(snk)
    r >> snk
    with pytest.raises(RuntimeError, match="still holding"):
        m.run(until=100)


def test_probability_route_splits():
    m = Model("split")
    src = Source(m, "src", rate=2.0)
    r = Route(m, "coin")
    a, b = Sink(m, "a"), Sink(m, "b")
    src >> r
    r.add(a, weight=0.5)
    r.add(b, weight=0.5)
    res = m.run(until=4000, seed=5)
    ka, kb = res.kpis["blocks"]["a"]["count"], res.kpis["blocks"]["b"]["count"]
    assert ka + kb == res.kpis["entities"]["disposed"]
    assert 0.45 < ka / (ka + kb) < 0.55


def test_queue_balk_and_renege_accounting():
    m = Model("impatient")
    src = Source(m, "src", rate=2.0)
    q = Queue(m, "q", capacity=3, max_wait=0.5)
    svc = Service(m, "slow", duration=Exponential(mean=5.0), resource=1)
    snk = Sink(m, "done")
    src >> q
    q >> svc
    svc >> snk
    res = m.run(until=200, seed=9)
    ent = res.kpis["entities"]
    qs = res.kpis["blocks"]["q"]
    assert qs["balked"] > 0 and qs["reneged"] > 0
    assert ent["dropped"] == qs["balked"] + qs["reneged"]
    assert ent["balance_ok"]


def test_determinism_same_seed_same_trace():
    r1 = mm1().run(until=500, seed=77)
    r2 = mm1().run(until=500, seed=77)
    assert r1.trace.records == r2.trace.records
    assert r1.scalars() == r2.scalars()
    r3 = mm1().run(until=500, seed=78)
    assert r3.scalars() != r1.scalars()


def test_warmup_resets_statistics():
    res = mm1().run(until=2000, warmup=500, seed=1)
    assert res.kpis["run"]["observed_duration"] == 1500
    # Arrivals counted only after the warmup boundary.
    lam_hat = res.kpis["entities"]["arrivals_observed"] / 1500
    assert 0.7 < lam_hat < 0.9
