"""Analytic queueing references — validation anchors for simulated models.

When a model reduces to a known queueing form, the analytic values are
computed and compared against the simulated confidence intervals. This is
Sargent's "comparison to other models" technique, automated (THEORY.md
Part 7): a simulated CI that fails to cover the analytic value means a bug —
in the model, the engine, or the assumptions — before it means a finding.

Conventions (Rossetti): c = servers, r = λ/μ (offered load),
ρ = λ/(cμ) (utilization). Stability requires ρ < 1.
"""

from __future__ import annotations

import math

from .blocks.queue import Queue
from .blocks.resources import Service
from .blocks.sink import Sink
from .blocks.source import Source
from .distributions import Distribution, Exponential
from .model import Model

# --------------------------------------------------------------------------
# Closed forms
# --------------------------------------------------------------------------


def mm1(lam: float, mu: float) -> dict:
    """M/M/1: exact L, Lq, W, Wq."""
    rho = lam / mu
    if rho >= 1:
        raise ValueError(f"Unstable: rho = {rho:.3f} >= 1 (queue grows forever)")
    return {
        "model": "M/M/1",
        "rho": rho,
        "L": rho / (1 - rho),
        "Lq": rho**2 / (1 - rho),
        "W": 1 / (mu - lam),
        "Wq": rho / (mu - lam),
        "exact": True,
    }


def erlang_c(c: int, r: float) -> float:
    """Probability an arrival must wait in M/M/c (r = λ/μ, requires r < c)."""
    rho = r / c
    summation = sum(r**k / math.factorial(k) for k in range(c))
    top = r**c / (math.factorial(c) * (1 - rho))
    return top / (summation + top)


def mmc(lam: float, mu: float, c: int) -> dict:
    """M/M/c: exact L, Lq, W, Wq via Erlang-C."""
    r = lam / mu
    rho = r / c
    if rho >= 1:
        raise ValueError(f"Unstable: rho = {rho:.3f} >= 1 (queue grows forever)")
    pw = erlang_c(c, r)
    wq = pw / (c * mu - lam)
    return {
        "model": f"M/M/{c}",
        "rho": rho,
        "erlang_c": pw,
        "Wq": wq,
        "W": wq + 1 / mu,
        "Lq": lam * wq,
        "L": lam * wq + r,
        "exact": True,
    }


def mg1(lam: float, service_mean: float, service_var: float) -> dict:
    """M/G/1: exact via Pollaczek–Khinchine."""
    mu = 1 / service_mean
    rho = lam / mu
    if rho >= 1:
        raise ValueError(f"Unstable: rho = {rho:.3f} >= 1 (queue grows forever)")
    lq = (lam**2 * service_var + rho**2) / (2 * (1 - rho))
    wq = lq / lam
    return {
        "model": "M/G/1 (Pollaczek–Khinchine)",
        "rho": rho,
        "Lq": lq,
        "Wq": wq,
        "W": wq + service_mean,
        "L": lq + rho,
        "exact": True,
    }


def kingman_wq(lam: float, service_mean: float, ca2: float, cs2: float, c: int = 1) -> dict:
    """G/G/c approximate Wq: Kingman/VUT for c=1, Allen–Cunneen style
    extension (Erlang-C base) for c>1. An approximation — label it as such."""
    mu = 1 / service_mean
    r = lam / mu
    rho = r / c
    if rho >= 1:
        raise ValueError(f"Unstable: rho = {rho:.3f} >= 1 (queue grows forever)")
    variability = (ca2 + cs2) / 2
    if c == 1:
        wq = variability * (rho / (1 - rho)) * service_mean
        name = "G/G/1 (Kingman/VUT approximation)"
    else:
        wq = variability * (erlang_c(c, r) / (c * mu - lam))
        name = f"G/G/{c} (Allen–Cunneen approximation)"
    return {
        "model": name,
        "rho": rho,
        "Wq": wq,
        "W": wq + service_mean,
        "Lq": lam * wq,
        "L": lam * wq + r,
        "exact": False,
    }


# --------------------------------------------------------------------------
# Model-shape detection
# --------------------------------------------------------------------------


def detect(model: Model) -> dict | None:
    """If the model is a single-station queueing system —
    Source(Poisson) → [Queue(fifo, unbounded, no reneging)] → Service → Sink —
    return the analytic reference and where to find the simulated KPIs.
    Returns None when the model doesn't reduce to a known form.
    """
    blocks = list(model.blocks.values())
    sources = [b for b in blocks if isinstance(b, Source)]
    queues = [b for b in blocks if isinstance(b, Queue)]
    services = [b for b in blocks if isinstance(b, Service)]
    sinks = [b for b in blocks if isinstance(b, Sink)]
    if (
        len(sources) != 1
        or len(services) != 1
        or len(sinks) != 1
        or len(queues) > 1
        or len(blocks) != len(sources) + len(queues) + len(services) + len(sinks)
    ):
        return None

    src, svc, sink = sources[0], services[0], sinks[0]
    if not isinstance(src.interarrival, Exponential):
        return None  # arrivals must be Poisson for these closed forms
    if queues:
        q = queues[0]
        if q.capacity is not None or q.max_wait is not None or q.discipline != "fifo":
            return None
        if src.outputs["out"] is not q or q.outputs["out"] is not svc:
            return None
        wq_kpi = f"{q.name}.wait.mean"
        lq_kpi = f"{q.name}.length.mean"
    else:
        if src.outputs["out"] is not svc:
            return None
        wq_kpi = f"{svc.pool.name}.wait.mean"
        lq_kpi = f"{svc.pool.name}.queue.mean"
    if svc.outputs["out"] is not sink:
        return None
    if not isinstance(svc.duration, Distribution):
        return None

    lam = src.interarrival.rate
    c = svc.pool.capacity
    dur = svc.duration
    service_mean = dur.mean()
    try:
        service_var = dur.variance()
    except NotImplementedError:
        return None

    if isinstance(dur, Exponential):
        analytic = mmc(lam, dur.rate, c) if c > 1 else mm1(lam, dur.rate)
    elif c == 1:
        analytic = mg1(lam, service_mean, service_var)
    else:
        cs2 = service_var / service_mean**2
        analytic = kingman_wq(lam, service_mean, ca2=1.0, cs2=cs2, c=c)

    return {
        "analytic": analytic,
        "kpis": {
            "W": f"{sink.name}.time_in_system.mean",
            "Wq": wq_kpi,
            "Lq": lq_kpi,
            "L": "wip.mean",
            "rho": f"{svc.pool.name}.utilization",
        },
    }


def check(model: Model, replications_result) -> dict | None:
    """Compare a ReplicationsResult against the analytic reference detected
    from ``model``. Returns per-metric coverage, or None if the model has no
    analytic reduction."""
    ref = detect(model)
    if ref is None:
        return None
    analytic = ref["analytic"]
    rows = []
    for metric, kpi_name in ref["kpis"].items():
        if metric not in analytic or kpi_name not in replications_result.kpi_samples:
            continue
        s = replications_result.summary(kpi_name)
        target = analytic[metric]
        covered = (
            s["n"] >= 2
            and not math.isnan(s["halfwidth"])
            and s["ci_low"] <= target <= s["ci_high"]
        )
        rows.append(
            {
                "metric": metric,
                "kpi": kpi_name,
                "analytic": target,
                "simulated_mean": s.get("mean"),
                "ci_low": s.get("ci_low"),
                "ci_high": s.get("ci_high"),
                "covered": covered,
            }
        )
    n_cov = sum(r["covered"] for r in rows)
    return {
        "reference": analytic["model"],
        "exact": analytic["exact"],
        "rho": analytic["rho"],
        "metrics": rows,
        "all_covered": n_cov == len(rows),
        "note": (
            "Approximate reference — expect small systematic deviations."
            if not analytic["exact"]
            else "Exact reference — a CI that misses it indicates a bug."
        ),
    }
