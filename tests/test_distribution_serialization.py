"""Round-trip serialization: from_dict(d.to_dict()) must rebuild a
distribution that is *stream-identical* — the strongest equivalence: given the
same Generator state, it produces the same draws. This is what lets a UI edit
a distribution and the server rebuild it without changing the model's
statistics."""

import numpy as np
import pytest

from simulation_engine.distributions import (
    Choice,
    Constant,
    Distribution,
    Empirical,
    Erlang,
    Exponential,
    Gamma,
    Lognormal,
    Normal,
    Pert,
    RateSchedule,
    Triangular,
    Uniform,
    Weibull,
    from_dict,
)

ALL_DISTS = [
    Constant(3.0),
    Uniform(1.0, 2.0),
    Exponential(mean=1.25),
    Exponential(rate=0.8),
    Triangular(1.0, 2.0, 5.0),
    Normal(mean=10.0, sd=2.0),
    Lognormal(mean=6.0, sd=3.0),
    Gamma(shape=2.0, scale=3.0),
    Erlang(k=3, mean=10.0),
    Weibull(shape=2.0, scale=4.0),
    Pert(1.5, 2.5, 5.0),
    Pert(1.5, 2.5, 5.0, lam=6.0),
    Empirical([1.0, 2.0, 3.0, 3.0, 7.5]),
    Choice([1.0, 2.0, 3.0], weights=[3, 1, 1]),
]


@pytest.mark.parametrize("dist", ALL_DISTS, ids=lambda d: type(d).__name__)
def test_round_trip_is_stream_identical(dist):
    rebuilt = from_dict(dist.to_dict())
    assert type(rebuilt) is type(dist)
    assert isinstance(rebuilt, Distribution)
    rng_a = np.random.Generator(np.random.PCG64(0))
    rng_b = np.random.Generator(np.random.PCG64(0))
    draws_a = [dist.sample(rng_a) for _ in range(100)]
    draws_b = [rebuilt.sample(rng_b) for _ in range(100)]
    assert draws_a == draws_b


def test_rate_schedule_round_trip():
    sched = RateSchedule([(0, 0.6), (180, 1.1), (360, 0.4)], cycle=960)
    rebuilt = from_dict(sched.to_dict())
    assert isinstance(rebuilt, RateSchedule)
    for t in (0.0, 100.0, 200.0, 500.0, 1000.0, 2000.0):
        assert rebuilt.rate_at(t) == sched.rate_at(t)
    rng_a = np.random.Generator(np.random.PCG64(0))
    rng_b = np.random.Generator(np.random.PCG64(0))
    t_a = t_b = 0.0
    for _ in range(50):
        t_a = sched.next_arrival(t_a, rng_a)
        t_b = rebuilt.next_arrival(t_b, rng_b)
        assert t_a == t_b


def test_exponential_rate_canonicalizes_to_mean():
    d = Exponential(rate=2.0)
    assert d.to_dict() == {"type": "Exponential", "args": {"mean": 0.5}}


def test_erlang_preserves_k_and_mean_exactly():
    d = Erlang(k=3, mean=10.0)
    assert d.to_dict()["args"] == {"k": 3, "mean": 10.0}
    rebuilt = from_dict(d.to_dict())
    assert isinstance(rebuilt, Erlang)
    assert rebuilt.scale == d.scale and rebuilt.shape == d.shape


def test_empirical_retains_data_in_to_dict_but_not_describe():
    d = Empirical([1.0, 2.0, 7.5])
    assert d.to_dict()["args"]["data"] == [1.0, 2.0, 7.5]
    assert "data" not in d.describe()
    assert d.describe()["n"] == 3


@pytest.mark.parametrize("dist", ALL_DISTS + [RateSchedule([(0, 1.0)])],
                         ids=lambda d: type(d).__name__)
def test_describe_leaks_no_private_keys(dist):
    assert not [k for k in dist.describe() if k.startswith("_")]


def test_from_dict_accepts_flat_describe_shape():
    d = from_dict({"type": "Exponential", "mean": 2.0})
    assert isinstance(d, Exponential) and d.mean() == 2.0


@pytest.mark.parametrize(
    "spec",
    [
        {"type": "NoSuchDist"},
        {"no_type": True},
        "not a dict",
        {"type": "Exponential", "args": {"nope": 1}},
        {"type": "Exponential", "args": {"mean": -1}},
        {"type": "Uniform", "args": {"low": 5, "high": 5}},
    ],
)
def test_from_dict_rejects_bad_specs(spec):
    with pytest.raises(ValueError):
        from_dict(spec)
