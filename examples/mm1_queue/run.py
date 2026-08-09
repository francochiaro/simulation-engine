"""M/M/1 queue — the canonical validation example.

Poisson arrivals (λ = 0.8/min) to a single exponential server (μ = 1.0/min):
utilization ρ = 0.8, and the analytic answers are exact (THEORY.md Part 7):

    L = ρ/(1-ρ) = 4      W  = 1/(μ-λ) = 5 min
    Lq = ρ²/(1-ρ) = 3.2  Wq = ρ/(μ-λ) = 4 min

The experiment runs independent replications and checks that every simulated
95% CI covers its analytic value — Sargent's "comparison to other models"
technique, automated. Run:

    uv run python examples/mm1_queue/run.py
"""

import os

from simulation_engine import Exponential, Model, Queue, Service, Sink, Source
from simulation_engine import theory_check
from simulation_engine.experiments import replicate
from simulation_engine.factors import describe_factors
from simulation_engine.viewer.build_viewer import build_viewer

LAM, MU = 0.8, 1.0

FACTORS = {
    "lam": {"label": "arrival rate λ (per min)", "min": 0.05, "max": 0.95, "step": 0.05},
    "mu": {"label": "service rate μ (per min)", "min": 0.5, "max": 2.0, "step": 0.05},
}


def make_model(lam: float = LAM, mu: float = MU) -> Model:
    m = Model("mm1_queue", time_unit="minutes")
    src = Source(m, "arrivals", rate=lam)
    q = Queue(m, "queue")
    svc = Service(m, "server", duration=Exponential(rate=mu), resource=1)
    snk = Sink(m, "done")
    src >> q
    q >> svc
    svc >> snk
    return m


def main() -> None:
    # Statistics: 20 replications of a long run with warm-up removed.
    reps = replicate(
        make_model, n=20, until=20_000, warmup=2_000, seed=11, keep_showcase=False
    )
    chk = theory_check.check(make_model(), reps)
    assert chk is not None

    print(f"Analytic reference: {chk['reference']}  (rho = {chk['rho']:.2f})")
    for r in chk["metrics"]:
        mark = "✓" if r["covered"] else "✗"
        print(
            f"  {mark} {r['metric']:>3}: analytic {r['analytic']:.3f}  "
            f"simulated 95% CI [{r['ci_low']:.3f}, {r['ci_high']:.3f}]"
        )
    print("all covered" if chk["all_covered"] else "COVERAGE FAILURE — investigate")

    # Animation: a short showcase run with the full trace.
    showcase = make_model().run(until=480, seed=11)
    out_dir = os.path.join(os.path.dirname(__file__), "runs", "latest")
    path = build_viewer(
        showcase,
        out_dir=out_dir,
        experiment={"kind": "replications", **reps.as_payload(), "theory_check": chk},
        factors=describe_factors(make_model, FACTORS),
        conceptual_model=open(
            os.path.join(os.path.dirname(__file__), "conceptual-model.md")
        ).read(),
    )
    print(f"\nviewer: {path}")


if __name__ == "__main__":
    main()
