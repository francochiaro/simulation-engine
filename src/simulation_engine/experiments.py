"""Experiments — the statistical layer over model runs.

One runner covers DES and static Monte Carlo:

- :func:`replicate` — n independent replications (fixed n or the sequential
  precision procedure of Hoad, Robinson & Davies 2007, with look-ahead),
  t-based confidence intervals on every KPI.
- :func:`sweep` — scenarios × replications with common random numbers, and
  paired-t CIs on scenario differences.
- :func:`monte_carlo` — static Monte Carlo over a plain function of sampled
  inputs, with distribution outputs and rank-correlation tornado data.
- :func:`welch_warmup` — Welch's graphical warm-up procedure as an analysis
  helper that recommends a truncation point.

Rules baked in (THEORY.md Part 5/9): every KPI ships with a CI half-width,
never a bare point estimate; scenario rankings report CIs on *differences*;
"cannot distinguish" is a valid answer.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

import numpy as np
from scipy import stats as sps

from .model import Model, RunResult
from .rng import StreamRegistry


# --------------------------------------------------------------------------
# Statistics helpers
# --------------------------------------------------------------------------

def ci_halfwidth(samples: Sequence[float], confidence: float = 0.95) -> float:
    """t-based confidence-interval half-width for the mean."""
    n = len(samples)
    if n < 2:
        return math.nan
    s = float(np.std(samples, ddof=1))
    t = float(sps.t.ppf(1 - (1 - confidence) / 2, n - 1))
    return t * s / math.sqrt(n)


def kpi_summary(samples: Sequence[float], confidence: float = 0.95) -> dict:
    arr = np.asarray([x for x in samples if not math.isnan(x)], dtype=float)
    n = len(arr)
    if n == 0:
        return {"n": 0}
    mean = float(arr.mean())
    hw = ci_halfwidth(arr, confidence)
    return {
        "n": n,
        "mean": mean,
        "std": float(arr.std(ddof=1)) if n > 1 else math.nan,
        "min": float(arr.min()),
        "max": float(arr.max()),
        "ci_low": mean - hw if not math.isnan(hw) else math.nan,
        "ci_high": mean + hw if not math.isnan(hw) else math.nan,
        "halfwidth": hw,
        "rel_precision": abs(hw / mean) if mean != 0 and not math.isnan(hw) else math.nan,
        "confidence": confidence,
    }


# --------------------------------------------------------------------------
# Replications
# --------------------------------------------------------------------------

@dataclass
class SequentialPolicy:
    """Sequential replication selection (Hoad, Robinson & Davies, WSC 2007).

    Adds replications until the CI half-width of ``kpi`` falls below
    ``precision`` (as a fraction of the running mean) and *stays* below it
    for ``k_limit`` look-ahead replications — the look-ahead guards against
    stopping on a lucky early convergence, the procedure's dominant failure
    mode without it.
    """

    kpi: str
    precision: float = 0.05
    confidence: float = 0.95
    min_reps: int = 5
    max_reps: int = 500
    k_limit: int = 5

    def look_ahead(self, n: int) -> int:
        return self.k_limit if n <= 100 else round(n * self.k_limit / 100)


@dataclass
class ReplicationsResult:
    kpi_samples: dict[str, list[float]]
    confidence: float
    showcase: RunResult | None = None
    sequential: dict | None = None

    @property
    def n(self) -> int:
        return len(next(iter(self.kpi_samples.values()), []))

    def summary(self, kpi: str) -> dict:
        return kpi_summary(self.kpi_samples[kpi], self.confidence)

    def table(self) -> dict[str, dict]:
        return {k: self.summary(k) for k in sorted(self.kpi_samples)}

    def cumulative(self, kpi: str) -> dict:
        """Cumulative mean + CI vs replication count — the standard
        convergence diagnostic chart."""
        xs = self.kpi_samples[kpi]
        out = {"n": [], "mean": [], "halfwidth": []}
        for i in range(2, len(xs) + 1):
            out["n"].append(i)
            out["mean"].append(float(np.mean(xs[:i])))
            out["halfwidth"].append(ci_halfwidth(xs[:i], self.confidence))
        return out

    def percentiles(self, kpi: str) -> dict:
        """P5/P10/P50/P90/P95 across replications — the decision-relevant
        summary of an output *distribution* (THEORY.md §8.1), complementing
        the CI on the mean."""
        arr = np.asarray(self.kpi_samples[kpi], dtype=float)
        arr = arr[~np.isnan(arr)]
        if arr.size == 0:
            return {f"p{q}": None for q in (5, 10, 50, 90, 95)}
        vals = np.percentile(arr, [5, 10, 50, 90, 95])
        return {f"p{q}": float(v) for q, v in zip((5, 10, 50, 90, 95), vals)}

    def as_payload(self) -> dict:
        """Everything the viewer's Monte Carlo tab needs, JSON-ready:
        summaries, raw per-replication samples, and percentiles per KPI."""
        payload = {
            "n_replications": self.n,
            "confidence": self.confidence,
            "kpi_table": self.table(),
            "kpi_samples": self.kpi_samples,
            "percentiles": {k: self.percentiles(k) for k in sorted(self.kpi_samples)},
        }
        if self.sequential:
            payload["sequential"] = self.sequential
        return payload


def _run_scalars(args) -> dict[str, float]:
    factory, params, run_kwargs, rep = args
    model = factory(**params) if params else factory()
    rr = model.run(replication=rep, trace_level="off", **run_kwargs)
    return rr.scalars()


def replicate(
    model_factory: Callable[..., Model],
    *,
    n: int | None = None,
    policy: SequentialPolicy | None = None,
    params: dict | None = None,
    until: float | None = None,
    warmup: float = 0.0,
    seed: int = 12345,
    confidence: float = 0.95,
    keep_showcase: bool = True,
    n_workers: int = 1,
) -> ReplicationsResult:
    """Run independent replications of ``model_factory(**params)``.

    Give either ``n`` (fixed) or ``policy`` (sequential precision). The first
    replication keeps its full trace as the ``showcase`` for the viewer.
    """
    if (n is None) == (policy is None):
        raise ValueError("replicate: give exactly one of n= or policy=")
    params = params or {}
    run_kwargs = {"until": until, "warmup": warmup, "seed": seed}
    samples: dict[str, list[float]] = {}
    showcase: RunResult | None = None

    def record(scalars: dict[str, float]) -> None:
        for k, v in scalars.items():
            samples.setdefault(k, []).append(v)

    def run_one(rep: int) -> None:
        nonlocal showcase
        model = model_factory(**params)
        level = "full" if (rep == 0 and keep_showcase) else "off"
        rr = model.run(replication=rep, trace_level=level, **run_kwargs)
        if rep == 0 and keep_showcase:
            showcase = rr
        record(rr.scalars())

    if n is not None:
        if n < 2:
            raise ValueError("replicate: n must be >= 2 (one run is an anecdote)")
        if n_workers > 1:
            run_one(0)
            with ProcessPoolExecutor(max_workers=n_workers) as pool:
                for scalars in pool.map(
                    _run_scalars,
                    [(model_factory, params, run_kwargs, rep) for rep in range(1, n)],
                ):
                    record(scalars)
        else:
            for rep in range(n):
                run_one(rep)
        return ReplicationsResult(samples, confidence, showcase)

    # Sequential procedure with look-ahead.
    assert policy is not None
    confidence = policy.confidence
    rep = 0
    d_series: list[float] = []

    def d_now() -> float:
        xs = samples.get(policy.kpi)
        if xs is None:
            raise KeyError(
                f"SequentialPolicy kpi {policy.kpi!r} not found among KPIs "
                f"{sorted(samples)}"
            )
        hw = ci_halfwidth(xs, confidence)
        m = float(np.mean(xs))
        return abs(hw / m) if m != 0 else math.inf

    for rep in range(policy.min_reps):
        run_one(rep)
    d_series.append(d_now())
    n_sol: int | None = None
    while rep + 1 < policy.max_reps:
        if d_series[-1] <= policy.precision:
            n_sol = rep + 1
            ahead = policy.look_ahead(n_sol)
            ok = True
            for _ in range(ahead):
                if rep + 1 >= policy.max_reps:
                    break
                rep += 1
                run_one(rep)
                d_series.append(d_now())
                if d_series[-1] > policy.precision:
                    ok = False
                    n_sol = None
                    break
            if ok:
                break
        else:
            rep += 1
            run_one(rep)
            d_series.append(d_now())

    return ReplicationsResult(
        samples,
        confidence,
        showcase,
        sequential={
            "kpi": policy.kpi,
            "target_precision": policy.precision,
            "achieved_precision": d_series[-1],
            "recommended_n": n_sol,
            "n_run": rep + 1,
            "converged": n_sol is not None,
            "d_series": d_series,
        },
    )


# --------------------------------------------------------------------------
# Scenario sweeps
# --------------------------------------------------------------------------

@dataclass
class SweepResult:
    scenarios: list[dict]
    results: list[ReplicationsResult]
    crn: bool
    confidence: float = 0.95

    def table(self, kpi: str) -> list[dict]:
        rows = []
        for sc, res in zip(self.scenarios, self.results):
            row = {"scenario": sc}
            row.update(res.summary(kpi))
            rows.append(row)
        return rows

    def compare(self, kpi: str, baseline: int = 0) -> list[dict]:
        """CI on the difference vs the baseline scenario. With CRN the
        replications are paired (much tighter). An interval containing 0
        means the data cannot distinguish the scenarios — say so."""
        base = np.asarray(self.results[baseline].kpi_samples[kpi], dtype=float)
        rows = []
        for i, (sc, res) in enumerate(zip(self.scenarios, self.results)):
            if i == baseline:
                continue
            other = np.asarray(res.kpi_samples[kpi], dtype=float)
            if self.crn and len(other) == len(base):
                diffs = other - base
                mean = float(diffs.mean())
                hw = ci_halfwidth(diffs, self.confidence)
            else:
                mean = float(other.mean() - base.mean())
                se = math.sqrt(
                    other.var(ddof=1) / len(other) + base.var(ddof=1) / len(base)
                )
                dof = min(len(other), len(base)) - 1
                hw = float(sps.t.ppf(1 - (1 - self.confidence) / 2, dof)) * se
            rows.append(
                {
                    "scenario": sc,
                    "diff_mean": mean,
                    "ci_low": mean - hw,
                    "ci_high": mean + hw,
                    "paired": self.crn and len(other) == len(base),
                    "distinguishable": not (mean - hw <= 0 <= mean + hw),
                }
            )
        return rows


def expand_grid(param_grid: dict[str, Sequence]) -> list[dict]:
    keys = sorted(param_grid)
    return [
        dict(zip(keys, combo))
        for combo in itertools.product(*(param_grid[k] for k in keys))
    ]


def sweep(
    model_factory: Callable[..., Model],
    param_grid: dict[str, Sequence] | list[dict],
    *,
    n: int,
    until: float | None = None,
    warmup: float = 0.0,
    seed: int = 12345,
    crn: bool = True,
    confidence: float = 0.95,
    n_workers: int = 1,
) -> SweepResult:
    """Scenarios × replications. With ``crn=True`` (default) every scenario
    reuses the same seeds/streams, pairing replication i across scenarios.

    NOTE (OFAT rule): a grid over multiple parameters estimates each
    combination honestly, but varying one factor at a time and reasoning
    about combinations is not valid — see THEORY.md Part 9.
    """
    scenarios = (
        expand_grid(param_grid) if isinstance(param_grid, dict) else list(param_grid)
    )
    if not scenarios:
        raise ValueError("sweep: no scenarios")
    results = []
    for i, sc in enumerate(scenarios):
        results.append(
            replicate(
                model_factory,
                n=n,
                params=sc,
                until=until,
                warmup=warmup,
                seed=seed if crn else seed + 100_003 * (i + 1),
                confidence=confidence,
                keep_showcase=(i == 0),
                n_workers=n_workers,
            )
        )
    return SweepResult(scenarios, results, crn, confidence)


# --------------------------------------------------------------------------
# Static Monte Carlo
# --------------------------------------------------------------------------

@dataclass
class MonteCarloResult:
    input_samples: dict[str, list[float]]
    output_samples: dict[str, list[float]]
    confidence: float = 0.95
    sequential: dict | None = None

    @property
    def n(self) -> int:
        return len(next(iter(self.output_samples.values()), []))

    def summary(self, output: str) -> dict:
        arr = np.asarray(self.output_samples[output], dtype=float)
        s = kpi_summary(arr, self.confidence)
        s.update(
            {
                "p5": float(np.percentile(arr, 5)),
                "p10": float(np.percentile(arr, 10)),
                "p50": float(np.percentile(arr, 50)),
                "p90": float(np.percentile(arr, 90)),
                "p95": float(np.percentile(arr, 95)),
            }
        )
        return s

    def table(self) -> dict[str, dict]:
        return {k: self.summary(k) for k in sorted(self.output_samples)}

    def prob_exceeds(self, output: str, threshold: float) -> float:
        arr = np.asarray(self.output_samples[output], dtype=float)
        return float((arr > threshold).mean())

    def tornado(self, output: str) -> list[dict]:
        """Spearman rank correlation of each input with the output —
        the standard importance ranking for a risk-analysis tornado chart."""
        y = np.asarray(self.output_samples[output], dtype=float)
        rows = []
        for name, xs in self.input_samples.items():
            rho = float(sps.spearmanr(xs, y).statistic)
            rows.append({"input": name, "spearman": rho})
        rows.sort(key=lambda r: abs(r["spearman"]), reverse=True)
        return rows

    def histogram(self, output: str, bins: int = 30) -> dict:
        arr = np.asarray(self.output_samples[output], dtype=float)
        counts, edges = np.histogram(arr, bins=bins)
        return {"counts": counts.tolist(), "edges": edges.tolist()}


def monte_carlo(
    fn: Callable[..., dict[str, float] | float],
    inputs: dict[str, object],
    *,
    n: int | None = None,
    precision: float | None = None,
    output: str | None = None,
    confidence: float = 0.95,
    min_n: int = 100,
    max_n: int = 1_000_000,
    seed: int = 12345,
) -> MonteCarloResult:
    """Static Monte Carlo: sample ``inputs`` (name -> Distribution), call
    ``fn(**sampled)``, collect output distribution(s).

    Give ``n`` (fixed) or ``precision`` (+ ``output`` when fn returns a dict)
    for sequential stopping on the relative CI half-width of the mean.
    Remember the mean converges at O(1/sqrt(n)); tail percentiles need far
    more samples than the mean.
    """
    from .distributions import Distribution

    if (n is None) == (precision is None):
        raise ValueError("monte_carlo: give exactly one of n= or precision=")
    for k, d in inputs.items():
        if not isinstance(d, Distribution):
            raise TypeError(f"monte_carlo input {k!r} must be a Distribution")

    streams = StreamRegistry(seed, 0)
    rngs = {k: streams.stream(f"mc.{k}") for k in inputs}
    in_samples: dict[str, list[float]] = {k: [] for k in inputs}
    out_samples: dict[str, list[float]] = {}

    def one() -> None:
        sampled = {k: d.sample(rngs[k]) for k, d in inputs.items()}  # type: ignore[union-attr]
        for k, v in sampled.items():
            in_samples[k].append(v)
        y = fn(**sampled)
        if isinstance(y, dict):
            for k, v in y.items():
                out_samples.setdefault(k, []).append(float(v))
        else:
            out_samples.setdefault("value", []).append(float(y))

    if n is not None:
        for _ in range(n):
            one()
        return MonteCarloResult(in_samples, out_samples, confidence)

    assert precision is not None
    for _ in range(min_n):
        one()
    key = output or next(iter(out_samples))
    if key not in out_samples:
        raise KeyError(f"monte_carlo: output {key!r} not in {sorted(out_samples)}")
    while True:
        xs = out_samples[key]
        hw = ci_halfwidth(xs, confidence)
        m = float(np.mean(xs))
        d = abs(hw / m) if m != 0 else math.inf
        if d <= precision or len(xs) >= max_n:
            return MonteCarloResult(
                in_samples,
                out_samples,
                confidence,
                sequential={
                    "output": key,
                    "target_precision": precision,
                    "achieved_precision": d,
                    "n": len(xs),
                    "converged": d <= precision,
                },
            )
        # Batch by 25% — checking the CI after every single draw is wasteful.
        for _ in range(max(min_n // 4, len(xs) // 4)):
            one()


# --------------------------------------------------------------------------
# Warm-up analysis (Welch's method)
# --------------------------------------------------------------------------

@dataclass
class WelchResult:
    grid: list[float]
    ensemble_mean: list[float]
    smoothed: list[float]
    recommended_warmup: float | None
    window: int
    n_replications: int

    def as_dict(self) -> dict:
        return {
            "grid": self.grid,
            "ensemble_mean": self.ensemble_mean,
            "smoothed": self.smoothed,
            "recommended_warmup": self.recommended_warmup,
            "window": self.window,
            "n_replications": self.n_replications,
        }


def _resample_step_series(
    series: list[tuple[float, float]], grid: np.ndarray
) -> np.ndarray:
    ts = np.asarray([t for t, _ in series])
    vs = np.asarray([v for _, v in series])
    idx = np.searchsorted(ts, grid, side="right") - 1
    idx = np.clip(idx, 0, len(vs) - 1)
    return vs[idx]


def welch_warmup(
    series_list: list[list[tuple[float, float]]],
    *,
    n_points: int = 400,
    window: int | None = None,
    tolerance: float = 0.10,
) -> WelchResult:
    """Welch's method on a level-monitor step series from R replications
    (R >= 5 recommended): average across replications at each grid point,
    smooth with a centered moving average, and recommend the earliest time
    after which the smoothed curve stays within ``tolerance`` of its final
    plateau (mean of the last half). Eyeball the plot before trusting it —
    Welch is a graphical method; the number is a starting point.
    """
    if len(series_list) < 2:
        raise ValueError("welch_warmup needs >= 2 replications (5+ recommended)")
    t_end = min(s[-1][0] for s in series_list)
    if t_end <= 0:
        raise ValueError("welch_warmup: series end at t=0")
    grid = np.linspace(0.0, t_end, n_points)
    stack = np.vstack([_resample_step_series(s, grid) for s in series_list])
    ensemble = stack.mean(axis=0)

    w = window if window is not None else max(n_points // 20, 5)
    w = min(w, n_points // 4)  # Welch's rule: window <= m/4
    smoothed = np.copy(ensemble)
    for i in range(len(ensemble)):
        half = min(w, i, len(ensemble) - 1 - i)
        smoothed[i] = ensemble[i - half : i + half + 1].mean()

    # Judge only where the centered window is full — the shrinking-window
    # head and tail of the smoothed curve are noise, not signal. The
    # recommendation is the first crossing of the plateau level (congestion
    # measures start biased low from an empty system and rise); a
    # band-holding criterion is too strict for autocorrelated series.
    lo, hi = w, len(smoothed) - w
    rec: float | None = None
    if hi > lo:
        core = smoothed[lo:hi]
        plateau = float(core[len(core) // 2 :].mean())
        start = core[0]
        if start <= plateau:
            hits = np.nonzero(core >= plateau * (1 - tolerance))[0]
        else:
            hits = np.nonzero(core <= plateau * (1 + tolerance))[0]
        if len(hits):
            rec = float(grid[lo + hits[0]])
    return WelchResult(
        grid=grid.tolist(),
        ensemble_mean=ensemble.tolist(),
        smoothed=smoothed.tolist(),
        recommended_warmup=rec,
        window=w,
        n_replications=len(series_list),
    )
