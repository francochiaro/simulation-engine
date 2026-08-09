"""Elevator bank in a tower — a transporter showcase.

A 20-floor tower with a 2-car service elevator bank. Morning up-peak: most
riders go lobby → upper floors; a background trickle moves between floors.
Cars move at 1 floor/2s, load/unload takes 8s each. v1 fleet semantics: one
request per trip, FIFO dispatch (no direction batching — that's the metro
upgrade in BACKLOG.md), which is honest for a freight/service lift.

KPIs: wait for a car (p95 matters, not the mean), total lobby→floor time,
car utilization. Sensitivity: 2 vs 3 cars. Run:

    uv run python examples/elevator/run.py
"""

import os

from simulation_engine import (
    Assign,
    Choice,
    Fleet,
    Model,
    RateSchedule,
    Ride,
    Sink,
    Source,
)
from simulation_engine.experiments import replicate, sweep
from simulation_engine.factors import describe_factors
from simulation_engine.report import build_report
from simulation_engine.viewer.build_viewer import build_viewer

FLOORS = 20
HOUR = 3600.0  # seconds
HORIZON = 3 * HOUR  # natural run length for the sidecar server

FACTORS = {
    "n_cars": {"label": "elevator cars", "min": 1, "max": 6, "step": 1},
}


def make_model(n_cars: int = 2) -> Model:
    m = Model("elevator_bank", time_unit="seconds")
    fleet = Fleet(
        m, "cars", n_cars=n_cars, speed=0.5,  # floors per second
        load_time=8.0, unload_time=8.0, home=0.0,
    )

    up_floor = Choice(values=list(range(2, FLOORS + 1)))

    lobby = Source(
        m, "lobby_riders",
        schedule=RateSchedule(  # riders/second: morning peak then calm
            [(0.0, 0.010), (1800.0, 0.045), (5400.0, 0.015)], cycle=3 * HOUR,
        ),
        entity_type="rider",
    ).at(80, 90)
    tag_up = Assign(
        m, "pick_floor",
        fn=lambda e, rng: e.attrs.update(
            {"from": 1.0, "to": float(up_floor.sample(rng))}
        ),
    ).at(260, 90)

    interfloor = Source(
        m, "interfloor_riders", rate=0.01, entity_type="staff"
    ).at(80, 220)
    tag_any = Assign(
        m, "pick_floors",
        fn=lambda e, rng: e.attrs.update(
            {
                "from": float(rng.integers(1, FLOORS + 1)),
                "to": float(rng.integers(1, FLOORS + 1)),
            }
        ),
    ).at(260, 220)

    ride = Ride(
        m, "elevator",
        fleet=fleet,
        from_pos=lambda e: e.attrs["from"],
        to_pos=lambda e: e.attrs["to"],
    ).at(440, 150)
    out = Sink(m, "arrived").at(620, 150)

    lobby >> tag_up
    tag_up >> ride
    interfloor >> tag_any
    tag_any >> ride
    ride >> out

    m.output("riders_delivered", lambda mm: mm.blocks["arrived"].count)
    m.output("wait_mean_s", lambda mm: mm.pools["cars"].wait.mean())
    m.output("wait_p95_s", lambda mm: mm.pools["cars"].wait.percentile(95))
    m.output(
        "door_to_door_mean_s",
        lambda mm: mm.blocks["arrived"].time_in_system.mean(),
    )
    return m


def main() -> None:
    showcase = make_model().run(until=3 * HOUR, seed=31)
    o = showcase.kpis["outputs"]
    print(
        f"showcase 3h: {o['riders_delivered']:.0f} riders, "
        f"wait mean {o['wait_mean_s']:.0f}s / p95 {o['wait_p95_s']:.0f}s, "
        f"door-to-door {o['door_to_door_mean_s']:.0f}s, "
        f"car utilization {showcase.kpis['pools']['cars']['utilization']:.1%}"
    )

    reps = replicate(
        make_model, n=15, until=3 * HOUR, seed=31, keep_showcase=False
    )
    sw = sweep(make_model, {"n_cars": [2, 3]}, n=15, until=3 * HOUR, seed=31)
    kpi = "wait_p95_s"
    print("\nscenarios (p95 wait, 95% CI):")
    for row in sw.table(kpi):
        print(f"  {row['scenario']}: {row['mean']:.0f}s ± {row['halfwidth']:.0f}")
    for row in sw.compare(kpi):
        verdict = "distinguishable" if row["distinguishable"] else "cannot distinguish"
        print(
            f"  Δ third car: {row['diff_mean']:+.0f}s "
            f"[{row['ci_low']:+.0f}, {row['ci_high']:+.0f}] — {verdict}"
        )

    out_dir = os.path.join(os.path.dirname(__file__), "runs", "latest")
    path = build_viewer(
        showcase,
        out_dir=out_dir,
        experiment={
            "kind": "replications + car-count sweep",
            **reps.as_payload(),
            "scenarios": {
                "kpi": kpi,
                "table": sw.table(kpi),
                "compare": sw.compare(kpi),
            },
        },
        factors=describe_factors(make_model, FACTORS),
        conceptual_model=open(
            os.path.join(os.path.dirname(__file__), "conceptual-model.md")
        ).read(),
    )
    print(f"\nviewer: {path}")

    report_path = os.path.join(out_dir, "report.md")
    build_report(
        question="Is a third elevator car worth it for the morning up-peak "
                 "(p95 wait-for-car)?",
        title="Elevator bank — 2 vs 3 cars",
        run_result=showcase,
        replications=reps,
        sweep_result=sw,
        sweep_kpi=kpi,
        conceptual_model=open(
            os.path.join(os.path.dirname(__file__), "conceptual-model.md")
        ).read(),
        assumptions=[
            "A1: peak arrival rate 0.045 riders/s — coarse badge-in counts",
            "A2: 8 s load / 8 s unload — small-sample observation",
        ],
        simplifications=[
            "S1: FIFO dispatch, one rider per trip (conservative vs group control)",
            "S2: no per-car capacity limit",
        ],
        kpi_prefixes=("riders_", "wait_", "door_", "cars."),
        out_path=report_path,
    )
    print(f"report: {report_path}")


if __name__ == "__main__":
    main()
