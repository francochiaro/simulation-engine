"""Pharmacy counters — 2 vs 3 under a lunch-hour rush with impatient customers.

Walk-ins arrive through a peaky 12 h day (nonstationary Poisson), join one
shared FIFO line, and renege when their patience runs out (lost sales).
Decision: is a third counter worth it?

Run:
    uv run python examples/pharmacy/run.py
"""

import os

from simulation_engine import (
    Exponential,
    Lognormal,
    Model,
    Pert,
    Queue,
    RateSchedule,
    Service,
    Sink,
    Source,
)
from simulation_engine import theory_check
from simulation_engine.experiments import SequentialPolicy, replicate, sweep
from simulation_engine.factors import describe_factors
from simulation_engine.report import build_report
from simulation_engine.viewer.build_viewer import build_viewer

DAY = 12 * 60.0  # 09:00-21:00, minutes
HORIZON = DAY  # natural run length for the sidecar server

FACTORS = {
    "n_counters": {"label": "counters", "min": 1, "max": 5, "step": 1},
    "peak_rate": {"label": "lunch peak (customers/min)", "min": 0.3, "max": 1.5, "step": 0.05},
}


def make_model(
    n_counters: int = 2,
    peak_rate: float = 0.90,
    service_time=Lognormal(mean=4.0, sd=2.5),
    patience=Pert(2.0, 6.0, 15.0),
) -> Model:
    m = Model("pharmacy", time_unit="minutes")

    src = Source(
        m, "walk_ins",
        schedule=RateSchedule(  # customers/min; t=0 is 09:00
            [(0.0, 0.30), (180.0, peak_rate), (300.0, 0.35), (540.0, 0.55), (660.0, 0.25)],
            cycle=DAY,
        ),
        entity_type="customer",
    ).at(80, 90)
    line = Queue(m, "line", max_wait=patience).at(260, 90)
    walked = Sink(m, "walked_out").at(260, 220)
    counters = Service(m, "counters", duration=service_time, resource=n_counters).at(440, 90)
    served = Sink(m, "served").at(620, 90)

    src >> line
    line >> counters
    line.to(walked, port="timeout")
    counters >> served

    m.output("customers_served", lambda mm: mm.blocks["served"].count)
    m.output("customers_lost", lambda mm: mm.blocks["walked_out"].count)
    m.output("wait_mean_min", lambda mm: mm.blocks["line"].wait.mean())
    m.output("wait_p95_min", lambda mm: mm.blocks["line"].wait.percentile(95))
    return m


def make_mm2_check(lam: float = 0.4, mu: float = 0.25) -> Model:
    """Simplified copy that reduces to M/M/2 (flat Poisson arrivals,
    exponential service, infinite patience) — the analytic anchor."""
    m = Model("pharmacy_mm2_check", time_unit="minutes")
    src = Source(m, "arrivals", rate=lam)
    q = Queue(m, "line")
    svc = Service(m, "counters", duration=Exponential(rate=mu), resource=2)
    snk = Sink(m, "served")
    src >> q
    q >> svc
    svc >> snk
    return m


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))

    # -- validation: analytic anchor on the simplified copy ---------------
    chk_reps = replicate(
        make_mm2_check, n=20, until=20_000, warmup=2_000, seed=17, keep_showcase=False
    )
    chk = theory_check.check(make_mm2_check(), chk_reps)
    assert chk is not None
    print(f"theory anchor {chk['reference']} (rho={chk['rho']:.2f}): "
          f"{'all CIs cover' if chk['all_covered'] else 'COVERAGE FAILURE'}")

    # -- validation: degenerate + extreme --------------------------------
    over = make_model(peak_rate=3.0).run(until=DAY, seed=1)
    calm = make_model(n_counters=8).run(until=DAY, seed=1)
    print(f"overload (peak 3.0/min): lost {over.kpis['outputs']['customers_lost']:.0f} "
          f"(should be large)")
    print(f"8 counters: lost {calm.kpis['outputs']['customers_lost']:.0f}, "
          f"wait p95 {calm.kpis['outputs']['wait_p95_min']:.2f} min (should be ~0)")

    # -- showcase day for the animation -----------------------------------
    showcase = make_model().run(until=DAY, seed=42)
    o = showcase.kpis["outputs"]
    print(f"showcase day: served {o['customers_served']:.0f}, "
          f"lost {o['customers_lost']:.0f}, "
          f"wait mean {o['wait_mean_min']:.1f} / p95 {o['wait_p95_min']:.1f} min")

    # -- replication sizing: ±10% relative on customers_lost --------------
    reps = replicate(
        make_model,
        policy=SequentialPolicy(kpi="customers_lost", precision=0.10, min_reps=5),
        until=DAY, seed=42, keep_showcase=False,
    )
    seq = reps.sequential
    print(f"sequential: n={seq['n_run']} achieved "
          f"{seq['achieved_precision']:.1%} on customers_lost "
          f"({'converged' if seq['converged'] else 'NOT converged'})")

    # -- the decision sweep: 2 vs 3 (vs 4) counters, CRN ------------------
    sw = sweep(make_model, {"n_counters": [2, 3, 4]}, n=max(15, reps.n),
               until=DAY, seed=42)
    kpi = "customers_lost"
    print("\ncustomers lost per day (95% CIs):")
    for row in sw.table(kpi):
        print(f"  {row['scenario']}: {row['mean']:.0f} ± {row['halfwidth']:.0f}")
    for row in sw.compare(kpi):
        verdict = "distinguishable" if row["distinguishable"] else "cannot distinguish"
        print(f"  Δ {row['scenario']}: {row['diff_mean']:+.0f} "
              f"[{row['ci_low']:+.0f}, {row['ci_high']:+.0f}] — {verdict}")

    # -- deliver -----------------------------------------------------------
    cm = open(os.path.join(here, "conceptual-model.md")).read()
    out_dir = os.path.join(here, "runs", "latest")
    path = build_viewer(
        showcase,
        out_dir=out_dir,
        experiment={
            "kind": "replications + counter sweep",
            **reps.as_payload(),
            "theory_check": chk,
            "scenarios": {"kpi": kpi, "table": sw.table(kpi), "compare": sw.compare(kpi)},
        },
        factors=describe_factors(make_model, FACTORS),
        conceptual_model=cm,
    )
    print(f"\nviewer: {path}")

    report_path = os.path.join(here, "report.md")
    build_report(
        question="Should the pharmacy add a third counter to stop losing "
                 "lunch-hour customers?",
        title="Pharmacy counters — 2 vs 3 under the lunch rush",
        run_result=showcase,
        replications=reps,
        theory=chk,
        sweep_result=sw,
        sweep_kpi=kpi,
        conceptual_model=cm,
        assumptions=[
            "A1: arrival profile 0.30 / 0.90 (lunch) / 0.35 / 0.55 / 0.25 per min — "
            "owner's description, no till data; peak height drives everything",
            "A2: service ~ Lognormal(4, 2.5) min — estimate, long tail understated",
            "A3: patience ~ Pert(2, 6, 15) min — estimate, nobody measured walkouts",
            "A4: ±10% relative accuracy on customers_lost suffices for the decision",
        ],
        simplifications=[
            "S1: one customer class (pickup vs consult folded together)",
            "S2: counters identical and always staffed (no breaks)",
            "S3: no balking at the door — join-then-leave captures the loss",
        ],
        next_steps=[
            "pull a week of till timestamps to fit the real arrival profile (A1)",
            "time 30 services to replace the Lognormal guess (A2)",
            "count walkouts for a few lunch hours to calibrate patience (A3)",
        ],
        kpi_prefixes=("customers_", "wait_", "counters.", "line.", "wip"),
        out_path=report_path,
    )
    print(f"report: {report_path}")


if __name__ == "__main__":
    main()
