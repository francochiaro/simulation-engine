import math

import pytest

from simulation_engine import (
    Choice,
    Constant,
    Erlang,
    Exponential,
    Lognormal,
    Normal,
    Pert,
    RateSchedule,
    Triangular,
    Uniform,
    Weibull,
)
from simulation_engine.rng import StreamRegistry


def rng():
    return StreamRegistry(7, 0).stream("t")


@pytest.mark.parametrize(
    "bad",
    [
        lambda: Exponential(),
        lambda: Exponential(mean=2, rate=0.5),
        lambda: Exponential(mean=-1),
        lambda: Uniform(5, 5),
        lambda: Triangular(0, 5, 3),
        lambda: Normal(mean=10, sd=8),  # cv too high -> silent truncation
        lambda: Lognormal(mean=-2, sd=1),
        lambda: Erlang(k=1.5, mean=3),
        lambda: Weibull(shape=0, scale=1),
        lambda: Pert(3, 2, 10),
        lambda: Choice([1, 2], weights=[1]),
        lambda: Constant(-1),
        lambda: RateSchedule([(5.0, 1.0)]),  # must start at 0
        lambda: RateSchedule([(0.0, 0.0)]),  # needs a positive rate
    ],
)
def test_impossible_parameters_fail_at_construction(bad):
    with pytest.raises(ValueError):
        bad()


def test_means_match_theory():
    g = rng()
    assert Exponential(mean=2.5).mean() == 2.5
    assert Exponential(rate=4).mean() == 0.25
    assert Triangular(0, 3, 9).mean() == 4.0
    assert Erlang(k=4, mean=8).cv() == pytest.approx(0.5)
    assert Exponential(mean=3).cv() == pytest.approx(1.0)
    # Lognormal parameterized by mean/sd of X itself.
    ln = Lognormal(mean=10, sd=3)
    xs = [ln.sample(g) for _ in range(40_000)]
    assert sum(xs) / len(xs) == pytest.approx(10, rel=0.02)


def test_normal_truncated_never_negative():
    g = rng()
    n = Normal(mean=1.0, sd=0.5)
    assert all(n.sample(g) >= 0 for _ in range(10_000))


def test_nonstationary_poisson_thinning_rates():
    # 2/min for the first 100, then 0.2/min: expect ~200 then ~20 arrivals.
    sched = RateSchedule([(0.0, 2.0), (100.0, 0.2)])
    g = rng()
    t, before, after = 0.0, 0, 0
    while t < 200.0:
        t = sched.next_arrival(t, g)
        if t < 100:
            before += 1
        elif t < 200:
            after += 1
    assert 160 <= before <= 240
    assert 8 <= after <= 36


def test_sampling_is_stream_deterministic():
    d = Exponential(mean=1.0)
    a = [d.sample(StreamRegistry(42, 3).stream("x")) for _ in range(1)]
    b = [d.sample(StreamRegistry(42, 3).stream("x")) for _ in range(1)]
    assert a == b
    assert not math.isclose(
        d.sample(StreamRegistry(42, 3).stream("x")),
        d.sample(StreamRegistry(42, 4).stream("x")),
    )
