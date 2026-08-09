"""report.build_report: every section renders from real artifacts, numbers
carry CIs, verdicts appear, and 'nan' never leaks into the markdown."""

from simulation_engine import Exponential, Model, Queue, Service, Sink, Source
from simulation_engine import theory_check
from simulation_engine.experiments import replicate, sweep
from simulation_engine.report import build_report


def make_model(lam: float = 0.8, mu: float = 1.0) -> Model:
    m = Model("mm1_report", time_unit="minutes")
    src = Source(m, "arrivals", rate=lam)
    q = Queue(m, "queue")
    svc = Service(m, "server", duration=Exponential(rate=mu), resource=1)
    snk = Sink(m, "done")
    src >> q
    q >> svc
    svc >> snk
    return m


def test_full_report(tmp_path):
    reps = replicate(make_model, n=5, until=2_000, warmup=200, seed=11)
    chk = theory_check.check(make_model(), reps)
    sw = sweep(make_model, {"mu": [1.0, 1.25]}, n=5, until=2_000, seed=11)
    out = tmp_path / "report.md"

    md = build_report(
        question="Is one server enough at λ=0.8?",
        title="M/M/1 capacity check",
        run_result=reps.showcase,
        replications=reps,
        theory=chk,
        sweep_result=sw,
        sweep_kpi="done.time_in_system.mean",
        conceptual_model="# Conceptual model — M/M/1\n\nstub",
        assumptions=["A1: arrivals are Poisson (definitional)"],
        simplifications=["S1: none"],
        next_steps=["collect real service times"],
        out_path=str(out),
    )

    for header in (
        "# M/M/1 capacity check", "## Question", "## Conceptual model",
        "## Validation evidence", "## Results — 5 replications",
        "## Scenario comparison", "## Assumptions register",
        "## Simplifications", "## What would sharpen the answer",
    ):
        assert header in md, header
    assert "Entity balance" in md and "Little's Law" in md
    assert "M/M/1" in md and "covered" in md
    # Every results row carries an interval, and verdicts are present.
    assert md.count("[") > 10
    assert "distinguishable" in md or "cannot distinguish" in md
    assert "P10 | P50 | P90".replace(" ", "") in md.replace(" ", "")
    assert "nan" not in md.lower()
    assert out.exists() and out.read_text() == md


def test_minimal_report_only_question():
    md = build_report(question="What if?")
    assert "## Question" in md and "What if?" in md
    assert "## Results" not in md and "## Scenario" not in md
    assert "nan" not in md.lower()
