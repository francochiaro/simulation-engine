"""Warehouse order fulfillment — a Tier-1 showcase.

Orders arrive through a peaky day (nonstationary Poisson), get picked by a
picker pool, accumulate onto dispatch carts (Batch), ride a forklift to the
dock (Fleet/Ride), are unloaded (Unbatch) and packed by packers whose station
suffers breakdowns (mtbf/mttr). KPI: order-to-dock time (TimeMeasure pair),
packer availability, lost demand.

Sweep: 3 vs 4 pickers × cart size 4 vs 8 — with CRN, so scenario differences
carry paired CIs. Run:

    uv run python examples/warehouse/run.py
"""

import os

from simulation_engine import (
    Batch,
    Exponential,
    Fleet,
    Lognormal,
    Model,
    Queue,
    RateSchedule,
    ResourcePool,
    Ride,
    Service,
    Sink,
    Source,
    TimeMeasureEnd,
    TimeMeasureStart,
    Triangular,
    Unbatch,
)
from simulation_engine.experiments import replicate, sweep
from simulation_engine.factors import describe_factors
from simulation_engine.viewer.build_viewer import build_viewer

DAY = 16 * 60.0  # two shifts, minutes

FACTORS = {
    "n_pickers": {"label": "pickers", "min": 1, "max": 8, "step": 1},
    "cart_size": {"label": "cart size (orders)", "min": 2, "max": 12, "step": 2},
}


def make_model(n_pickers: int = 3, cart_size: int = 4) -> Model:
    m = Model("warehouse", time_unit="minutes")

    packers = ResourcePool(
        m, "packers", capacity=3,
        mtbf=Exponential(mean=180.0), mttr=Triangular(5, 12, 30),
    )

    src = Source(
        m, "orders",
        schedule=RateSchedule(  # per-minute order rate over the day
            [(0.0, 0.6), (180.0, 1.1), (420.0, 0.7), (600.0, 1.2), (840.0, 0.4)],
            cycle=DAY,
        ),
        entity_type="order",
    ).at(80, 90)

    t0 = TimeMeasureStart(m, "clock_in", measure="order_to_dock").at(80, 220)
    pick_q = Queue(m, "pick_queue", max_wait=45.0).at(260, 90)
    lost = Sink(m, "lost_demand").at(260, 220)
    pick = Service(
        m, "picking", duration=Lognormal(mean=6.0, sd=3.0), resource=n_pickers
    ).at(440, 90)
    cart = Batch(m, "cart", size=cart_size, timeout=20.0).at(620, 90)
    haul = Ride(
        m, "forklift_haul", fleet=Fleet(m, "forklifts", n_cars=2, speed=80.0, home=0.0),
        from_pos=0.0, to_pos=120.0,
    ).at(800, 90)
    unload = Unbatch(m, "unload").at(980, 90)
    packing = Service(
        m, "packing", duration=Triangular(1.5, 2.5, 5.0), resource=packers
    ).at(1160, 90)
    t1 = TimeMeasureEnd(m, "clock_out", measure="order_to_dock").at(1160, 220)
    dock = Sink(m, "dispatched").at(1340, 90)

    src >> t0
    t0 >> pick_q
    pick_q >> pick
    pick_q.to(lost, port="timeout")
    pick >> cart
    cart >> haul
    haul >> unload
    unload >> packing
    packing >> t1
    t1 >> dock

    m.output("orders_dispatched", lambda mm: mm.blocks["dispatched"].count)
    m.output("orders_lost", lambda mm: mm.blocks["lost_demand"].count)
    m.output(
        "order_to_dock_mean", lambda mm: mm.blocks["clock_out"].elapsed.mean()
    )
    return m


def main() -> None:
    # One observed day, animated.
    showcase = make_model().run(until=DAY, seed=7)
    k = showcase.kpis
    print(
        f"showcase day: dispatched {k['outputs']['orders_dispatched']:.0f}, "
        f"lost {k['outputs']['orders_lost']:.0f}, "
        f"order→dock mean {k['outputs']['order_to_dock_mean']:.1f} min, "
        f"packer availability {k['pools']['packers']['availability']:.1%}"
    )

    # Replications for the base configuration (terminating: one day).
    reps = replicate(make_model, n=15, until=DAY, seed=7, keep_showcase=False)

    # Scenario sweep with CRN: pickers × cart size.
    sw = sweep(
        make_model,
        {"n_pickers": [3, 4], "cart_size": [4, 8]},
        n=15,
        until=DAY,
        seed=7,
    )
    kpi = "order_to_dock_mean"
    print("\nscenarios (order→dock mean + lost orders, 95% CIs):")
    for row, lost_row in zip(sw.table(kpi), sw.table("orders_lost")):
        print(
            f"  {row['scenario']}: {row['mean']:.1f} ± {row['halfwidth']:.1f} min, "
            f"lost {lost_row['mean']:.0f} ± {lost_row['halfwidth']:.0f}"
        )
    print("\nvs baseline {'cart_size': 4, 'n_pickers': 3}:")
    for row in sw.compare(kpi):
        verdict = "distinguishable" if row["distinguishable"] else "cannot distinguish"
        print(
            f"  {row['scenario']}: Δ {row['diff_mean']:+.1f} "
            f"[{row['ci_low']:+.1f}, {row['ci_high']:+.1f}] — {verdict}"
        )

    out_dir = os.path.join(os.path.dirname(__file__), "runs", "latest")
    path = build_viewer(
        showcase,
        out_dir=out_dir,
        experiment={
            "kind": "replications + CRN sweep",
            **reps.as_payload(),
            "scenarios": {
                "kpi": kpi,
                "table": sw.table(kpi),
                "compare": sw.compare(kpi),
            },
        },
        factors=describe_factors(make_model, FACTORS),
    )
    print(f"\nviewer: {path}")


if __name__ == "__main__":
    main()
