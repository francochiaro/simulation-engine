"""Probability distributions for input modeling.

Design rules (see THEORY.md Part 4):

- Every distribution validates its parameters at construction — an impossible
  parameterization fails *before* the run, with a corrective message.
- Every distribution knows its ``mean()`` (and ``cv()`` where defined) so the
  theory-check layer can compute analytic references.
- Sampling takes an explicit ``numpy.random.Generator`` — distributions hold
  no RNG state, which is what makes streams/CRN work.
- Duration-like distributions never return negative values (Normal is
  truncated at zero and says so loudly in its docs).
"""

from __future__ import annotations

import bisect
import math
from abc import ABC, abstractmethod
from collections.abc import Sequence

import numpy as np


class Distribution(ABC):
    """Base class for all input distributions."""

    @abstractmethod
    def sample(self, rng: np.random.Generator) -> float: ...

    @abstractmethod
    def mean(self) -> float: ...

    def variance(self) -> float:
        raise NotImplementedError(f"{type(self).__name__} has no closed-form variance")

    def cv(self) -> float:
        """Coefficient of variation (std / mean). The single most diagnostic
        number for queueing behavior — see the Kingman/VUT equation."""
        m = self.mean()
        if m == 0:
            raise ValueError("cv undefined for zero mean")
        return math.sqrt(self.variance()) / m

    def describe(self) -> dict:
        d: dict[str, object] = {"type": type(self).__name__}
        d.update(
            {k: v for k, v in vars(self).items() if isinstance(v, (int, float, str))}
        )
        return d


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(msg)


class Constant(Distribution):
    """A degenerate distribution. Legitimate for genuinely fixed durations —
    but if you are using this to 'simplify' a random quantity, you are
    committing the cardinal sin of input modeling (THEORY.md §4.1)."""

    def __init__(self, value: float):
        _require(value >= 0, f"Constant value must be >= 0, got {value}")
        self.value = float(value)

    def sample(self, rng: np.random.Generator) -> float:
        return self.value

    def mean(self) -> float:
        return self.value

    def variance(self) -> float:
        return 0.0


class Uniform(Distribution):
    def __init__(self, low: float, high: float):
        _require(low < high, f"Uniform requires low < high, got [{low}, {high}]")
        self.low, self.high = float(low), float(high)

    def sample(self, rng: np.random.Generator) -> float:
        return rng.uniform(self.low, self.high)

    def mean(self) -> float:
        return (self.low + self.high) / 2

    def variance(self) -> float:
        return (self.high - self.low) ** 2 / 12


class Exponential(Distribution):
    """Exponential — interarrival times of a Poisson process. cv = 1.

    Parameterize with exactly one of ``mean`` or ``rate`` (rate = 1/mean).
    """

    def __init__(self, mean: float | None = None, rate: float | None = None):
        _require(
            (mean is None) != (rate is None),
            "Exponential takes exactly one of mean= or rate=",
        )
        if rate is not None:
            _require(rate > 0, f"Exponential rate must be > 0, got {rate}")
            mean = 1.0 / rate
        assert mean is not None
        _require(mean > 0, f"Exponential mean must be > 0, got {mean}")
        self._mean = float(mean)

    @property
    def rate(self) -> float:
        return 1.0 / self._mean

    def sample(self, rng: np.random.Generator) -> float:
        return rng.exponential(self._mean)

    def mean(self) -> float:
        return self._mean

    def variance(self) -> float:
        return self._mean**2


class Triangular(Distribution):
    """Triangular(min, mode, max) — the data-poverty fallback when an SME can
    only give you three numbers. Cannot represent a long right tail; flag its
    use in the assumptions register (THEORY.md §4.3)."""

    def __init__(self, low: float, mode: float, high: float):
        _require(
            low <= mode <= high and low < high,
            f"Triangular requires low <= mode <= high (and low < high), "
            f"got ({low}, {mode}, {high})",
        )
        self.low, self.mode, self.high = float(low), float(mode), float(high)

    def sample(self, rng: np.random.Generator) -> float:
        return rng.triangular(self.low, self.mode, self.high)

    def mean(self) -> float:
        return (self.low + self.mode + self.high) / 3

    def variance(self) -> float:
        a, m, b = self.low, self.mode, self.high
        return (a**2 + m**2 + b**2 - a * m - a * b - m * b) / 18


class Normal(Distribution):
    """Normal truncated at zero (resampled). A plain normal is never a valid
    duration — it always has positive probability of a negative value. Use
    Lognormal or Gamma for right-skewed durations; use this only for
    symmetric, tightly concentrated quantities (cv << 1)."""

    def __init__(self, mean: float, sd: float):
        _require(sd > 0, f"Normal sd must be > 0, got {sd}")
        _require(mean > 0, f"Normal(truncated) mean must be > 0, got {mean}")
        if sd / mean > 0.5:
            raise ValueError(
                f"Normal with cv={sd / mean:.2f} > 0.5 would truncate heavily at "
                f"zero and no longer mean what you think. Use Lognormal or Gamma."
            )
        self._mean, self.sd = float(mean), float(sd)

    def sample(self, rng: np.random.Generator) -> float:
        # cv <= 0.5 makes rejection loops vanishingly rare.
        while True:
            x = rng.normal(self._mean, self.sd)
            if x >= 0:
                return x

    def mean(self) -> float:
        return self._mean

    def variance(self) -> float:
        return self.sd**2


class Lognormal(Distribution):
    """Lognormal parameterized by the mean and sd of X itself (NOT of ln X —
    that classic confusion is handled here so model authors never touch
    mu/sigma)."""

    def __init__(self, mean: float, sd: float):
        _require(mean > 0, f"Lognormal mean must be > 0, got {mean}")
        _require(sd > 0, f"Lognormal sd must be > 0, got {sd}")
        self._mean, self.sd = float(mean), float(sd)
        var = sd**2
        self._sigma2 = math.log(1 + var / mean**2)
        self._mu = math.log(mean) - self._sigma2 / 2

    def sample(self, rng: np.random.Generator) -> float:
        return rng.lognormal(self._mu, math.sqrt(self._sigma2))

    def mean(self) -> float:
        return self._mean

    def variance(self) -> float:
        return self.sd**2


class Gamma(Distribution):
    def __init__(self, shape: float, scale: float):
        _require(shape > 0, f"Gamma shape must be > 0, got {shape}")
        _require(scale > 0, f"Gamma scale must be > 0, got {scale}")
        self.shape, self.scale = float(shape), float(scale)

    def sample(self, rng: np.random.Generator) -> float:
        return rng.gamma(self.shape, self.scale)

    def mean(self) -> float:
        return self.shape * self.scale

    def variance(self) -> float:
        return self.shape * self.scale**2


class Erlang(Gamma):
    """Erlang-k: sum of k exponentials. cv = 1/sqrt(k) — the standard way to
    say 'like exponential but less variable'."""

    def __init__(self, k: int, mean: float):
        _require(int(k) == k and k >= 1, f"Erlang k must be a positive integer, got {k}")
        _require(mean > 0, f"Erlang mean must be > 0, got {mean}")
        super().__init__(shape=int(k), scale=mean / int(k))
        self.k = int(k)


class Weibull(Distribution):
    """Weibull(shape, scale) — time to failure. shape < 1: infant mortality;
    shape = 1: exponential; shape > 1: wear-out."""

    def __init__(self, shape: float, scale: float):
        _require(shape > 0, f"Weibull shape must be > 0, got {shape}")
        _require(scale > 0, f"Weibull scale must be > 0, got {scale}")
        self.shape, self.scale = float(shape), float(scale)

    def sample(self, rng: np.random.Generator) -> float:
        return self.scale * rng.weibull(self.shape)

    def mean(self) -> float:
        return self.scale * math.gamma(1 + 1 / self.shape)

    def variance(self) -> float:
        g1 = math.gamma(1 + 1 / self.shape)
        g2 = math.gamma(1 + 2 / self.shape)
        return self.scale**2 * (g2 - g1**2)


class Pert(Distribution):
    """PERT(min, mode, max) — a smoothed triangular (scaled Beta), the
    standard choice for expert-estimated activity durations."""

    def __init__(self, low: float, mode: float, high: float, lam: float = 4.0):
        _require(
            low <= mode <= high and low < high,
            f"Pert requires low <= mode <= high (and low < high), "
            f"got ({low}, {mode}, {high})",
        )
        self.low, self.mode, self.high, self.lam = (
            float(low),
            float(mode),
            float(high),
            float(lam),
        )
        rng_span = self.high - self.low
        self._alpha = 1 + lam * (self.mode - self.low) / rng_span
        self._beta = 1 + lam * (self.high - self.mode) / rng_span

    def sample(self, rng: np.random.Generator) -> float:
        return self.low + (self.high - self.low) * rng.beta(self._alpha, self._beta)

    def mean(self) -> float:
        return (self.low + self.lam * self.mode + self.high) / (self.lam + 2)

    def variance(self) -> float:
        a, b = self._alpha, self._beta
        beta_var = a * b / ((a + b) ** 2 * (a + b + 1))
        return (self.high - self.low) ** 2 * beta_var


class Empirical(Distribution):
    """Resample observed data (with replacement). Cannot extrapolate beyond
    the observed min/max — it has no tail."""

    def __init__(self, data: Sequence[float]):
        _require(len(data) > 0, "Empirical requires at least one observation")
        _require(all(x >= 0 for x in data), "Empirical data must be non-negative")
        self.data = np.asarray(data, dtype=float)

    def sample(self, rng: np.random.Generator) -> float:
        return float(rng.choice(self.data))

    def mean(self) -> float:
        return float(self.data.mean())

    def variance(self) -> float:
        return float(self.data.var(ddof=1)) if len(self.data) > 1 else 0.0

    def describe(self) -> dict:
        return {"type": "Empirical", "n": int(len(self.data)), "mean": self.mean()}


class Choice(Distribution):
    """Discrete choice over values with optional weights (probabilities)."""

    def __init__(self, values: Sequence[float], weights: Sequence[float] | None = None):
        _require(len(values) > 0, "Choice requires at least one value")
        self.values = np.asarray(values, dtype=float)
        if weights is None:
            self.probs = np.full(len(values), 1.0 / len(values))
        else:
            _require(
                len(weights) == len(values),
                f"Choice got {len(values)} values but {len(weights)} weights",
            )
            w = np.asarray(weights, dtype=float)
            _require(bool((w >= 0).all()) and w.sum() > 0, "Choice weights must be >= 0 and sum > 0")
            self.probs = w / w.sum()

    def sample(self, rng: np.random.Generator) -> float:
        return float(rng.choice(self.values, p=self.probs))

    def mean(self) -> float:
        return float((self.values * self.probs).sum())

    def variance(self) -> float:
        m = self.mean()
        return float((self.probs * (self.values - m) ** 2).sum())

    def describe(self) -> dict:
        return {
            "type": "Choice",
            "values": self.values.tolist(),
            "probs": self.probs.tolist(),
        }


class RateSchedule:
    """Piecewise-constant arrival rate λ(t) for a nonstationary Poisson
    process, sampled by thinning (the standard method — THEORY.md §4.5).

    ``breakpoints`` are (start_time, rate) pairs in model time units; the last
    rate holds forever (or the schedule repeats if ``cycle`` is set).
    """

    def __init__(self, breakpoints: Sequence[tuple[float, float]], cycle: float | None = None):
        _require(len(breakpoints) > 0, "RateSchedule requires at least one (time, rate) pair")
        times = [t for t, _ in breakpoints]
        _require(times == sorted(times), "RateSchedule breakpoints must be time-sorted")
        _require(times[0] == 0, "RateSchedule must start at time 0")
        _require(all(r >= 0 for _, r in breakpoints), "RateSchedule rates must be >= 0")
        if cycle is not None:
            _require(cycle > times[-1], "RateSchedule cycle must exceed the last breakpoint")
        self.breakpoints = [(float(t), float(r)) for t, r in breakpoints]
        self.cycle = cycle
        self.rate_max = max(r for _, r in breakpoints)
        _require(self.rate_max > 0, "RateSchedule needs at least one positive rate")
        self._times = [t for t, _ in self.breakpoints]

    def rate_at(self, t: float) -> float:
        if self.cycle is not None:
            t = t % self.cycle
        i = bisect.bisect_right(self._times, t) - 1
        return self.breakpoints[i][1]

    def next_arrival(self, t: float, rng: np.random.Generator) -> float:
        """Time of the next arrival strictly after ``t``, by thinning."""
        while True:
            t += rng.exponential(1.0 / self.rate_max)
            if rng.uniform() <= self.rate_at(t) / self.rate_max:
                return t

    def describe(self) -> dict:
        return {
            "type": "RateSchedule",
            "breakpoints": self.breakpoints,
            "cycle": self.cycle,
        }
