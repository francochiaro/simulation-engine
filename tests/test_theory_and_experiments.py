import pytest

from simulation_engine import Exponential, Model, Pert, Queue, Service, Sink, Source
from simulation_engine import theory_check
from simulation_engine.experiments import (
    SequentialPolicy,
    monte_carlo,
    replicate,
    sweep,
    welch_warmup,
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


def mmc(lam=2.4, mu=1.0, c=3):
    m = Model("mmc", time_unit="minutes")
    src = Source(m, "arrivals", rate=lam)
    svc = Service(m, "servers", duration=Exponential(rate=mu), resource=c)
    snk = Sink(m, "done")
    src >> svc
    svc >> snk
    return m


# The product's core promise: simulated CIs cover the exact analytic values.
def test_mm1_cis_cover_analytics():
    reps = replicate(mm1, n=20, until=20_000, warmup=2_000, seed=11, keep_showcase=False)
    chk = theory_check.check(mm1(), reps)
    assert chk is not None and chk["exact"]
    assert chk["reference"] == "M/M/1"
    assert chk["all_covered"], chk["metrics"]


def test_mmc_cis_cover_analytics():
    reps = replicate(mmc, n=20, until=15_000, warmup=1_500, seed=19, keep_showcase=False)
    chk = theory_check.check(mmc(), reps)
    assert chk is not None and chk["exact"]
    assert chk["reference"] == "M/M/3"
    assert chk["all_covered"], chk["metrics"]


def test_little_residual_small_on_every_run():
    res = mm1().run(until=20_000, warmup=2_000, seed=4, trace_level="off")
    assert res.kpis["little"]["residual_rel"] < 0.02


def test_analytic_formulas():
    r = theory_check.mm1(0.8, 1.0)
    assert r["L"] == pytest.approx(4.0)
    assert r["Wq"] == pytest.approx(4.0)
    r = theory_check.mmc(2.4, 1.0, 3)
    # Erlang-C sanity: rho = 0.8, P(wait) ~ 0.6472 for c=3.
    assert r["rho"] == pytest.approx(0.8)
    assert r["erlang_c"] == pytest.approx(0.6472, abs=0.001)
    with pytest.raises(ValueError, match="Unstable"):
        theory_check.mm1(1.2, 1.0)


def test_sequential_policy_converges_with_lookahead():
    reps = replicate(
        mm1,
        policy=SequentialPolicy(
            kpi="done.time_in_system.mean", precision=0.08, min_reps=5, k_limit=3
        ),
        until=10_000,
        warmup=1_000,
        seed=13,
        keep_showcase=False,
    )
    seq = reps.sequential
    assert seq["converged"]
    assert seq["achieved_precision"] <= 0.08
    assert seq["n_run"] >= seq["recommended_n"]


def test_sweep_crn_pairs_and_distinguishes():
    res = sweep(
        mm1, {"mu": [1.0, 1.25]}, n=10, until=10_000, warmup=1_000, seed=17
    )
    cmp_rows = res.compare("done.time_in_system.mean")
    assert cmp_rows[0]["paired"]
    assert cmp_rows[0]["diff_mean"] < 0
    assert cmp_rows[0]["distinguishable"]


def test_monte_carlo_merge_bias_and_prob():
    mc = monte_carlo(
        lambda a, b: {"dur": max(a, b)},
        {"a": Pert(5, 10, 30), "b": Pert(5, 10, 30)},
        n=20_000,
        seed=23,
    )
    s = mc.summary("dur")
    assert s["mean"] > 10  # E[max] > max of modes: the flaw of averages
    assert 0 < mc.prob_exceeds("dur", 20) < 0.5
    tor = mc.tornado("dur")
    assert {r["input"] for r in tor} == {"a", "b"}


def test_monte_carlo_sequential_precision():
    mc = monte_carlo(
        lambda x: x, {"x": Pert(0, 10, 20)}, precision=0.02, seed=29, min_n=200
    )
    assert mc.sequential["converged"]
    assert mc.summary("value")["rel_precision"] <= 0.02


def test_welch_recovers_known_warmup():
    # Synthetic congestion curve: ramps 0 -> 10 over t in [0, 100], then flat.
    def series(offset):
        return [(float(t), min(10.0, t / 10.0) + offset) for t in range(0, 1000, 2)]

    w = welch_warmup([series(0.0), series(0.05), series(-0.05), series(0.02), series(-0.02)])
    assert w.recommended_warmup is not None
    assert 60 <= w.recommended_warmup <= 160
