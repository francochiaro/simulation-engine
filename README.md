# simulation-engine

[![CI](https://github.com/francochiaro/simulation-engine/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/francochiaro/simulation-engine/actions/workflows/ci.yml)

Agent-driven discrete-event and Monte Carlo simulation. An AnyLogic-style
workflow — conceptual model, validated software model, replications with
confidence intervals, sensitivity scenarios, animated visualization — where
the model is built **conversationally by an agent (Claude Code)** instead of
through a GUI: you describe the system, the agent interviews you into a
conceptual model, generates the block-DSL model, validates it against
queueing theory, and hands you a link to watch it run.

**Grounded in the classic simulation literature** — Banks, Law, Robinson,
Sargent, Hoad et al., Ross, Kleinrock, Hopp & Spearman. See
[THEORY.md](THEORY.md): every design rule in this codebase traces to a
section there.

## What it does

- **Discrete-event simulation** of systems where entities compete for limited
  resources: production lines, warehouses, service counters, elevators,
  ports…
- **Static Monte Carlo** for questions with no clock: cost rollups, project
  durations, risk sums.
- **Experiments with honest statistics**: independent replications with
  t-based confidence intervals on every KPI; automatic replication-count
  selection (Hoad–Robinson–Davies sequential procedure with look-ahead);
  common-random-number scenario sweeps with paired CIs on differences; Welch
  warm-up analysis.
- **Built-in validation**: pre-run model checks (unconnected ports, resource
  leaks, impossible parameters), a Little's Law residual on every run, entity
  balance accounting, and automatic comparison against exact queueing
  formulas (M/M/1, M/M/c, M/G/1) whenever the model reduces to one.
- **A self-contained replay viewer**: one double-clickable HTML file per run —
  animated entities over the block diagram, charts advancing with simulated
  time, a playback-speed slider and scrubber, and a report tab with CIs,
  consistency checks, and experiment tables.

## Quickstart

```bash
git clone git@github.com:francochiaro/simulation-engine.git
cd simulation-engine
uv sync
uv run python examples/mm1_queue/run.py
# → prints the analytic-coverage table and the path to the viewer HTML
```

An M/M/1 queue in the block DSL:

```python
from simulation_engine import Exponential, Model, Queue, Service, Sink, Source

m = Model("mm1", time_unit="minutes")
src = Source(m, "arrivals", rate=0.8)                  # Poisson arrivals
q   = Queue(m, "queue")                                # explicit waiting line
svc = Service(m, "server", duration=Exponential(rate=1.0), resource=1)
snk = Sink(m, "done")
src >> q; q >> svc; svc >> snk

result = m.run(until=20_000, warmup=2_000, seed=11)
print(result.kpis["little"])       # L vs λ·W residual — a free bug detector
```

Replications, theory check, and the viewer:

```python
from simulation_engine.experiments import replicate
from simulation_engine import theory_check
from simulation_engine.viewer.build_viewer import build_viewer

reps = replicate(make_model, n=20, until=20_000, warmup=2_000, seed=11)
chk  = theory_check.check(make_model(), reps)   # CIs must cover W, Wq, L, Lq, ρ
path = build_viewer(make_model().run(until=480, seed=11), out_dir="runs/demo")
# open path in a browser
```

## Architecture — three layers, and who writes what

```
Layer 3  Experiment runner   scenarios × replications, CRN seeding, warm-up,
                             CIs, sequential stopping, parallel workers
Layer 2  Block DSL           Source · Queue · Delay · Service · ResourcePool ·
                             Seize/Release · Route · Assign · Sink
                             ← THE ONLY LAYER MODEL AUTHORS (OR AGENTS) WRITE
Layer 1  SimPy 4             generators, event heap, interrupts
                             ← never exposed; swappable
```

Why a block DSL instead of raw SimPy: LLM-generated process code fails
*silently* — a missing `yield` runs and reports plausible wrong numbers
(the research literature on LLM-built simulations converges on this). A block
graph has **zero `yield`s in model code** and is **validatable before it
runs**. Every state transition passes through a block, so the event trace and
the KPIs are complete by construction.

Design rules the codebase enforces:

- **Resources are identity-bearing** (`pool#3`), never anonymous slots — the
  trace can say *which* server an entity used; pools report per-unit busy time.
- **One RNG stream per named stochastic source** per replication
  (`SeedSequence`-derived) — reproducible runs, and common random numbers
  across scenarios for free.
- **Every KPI ships with a confidence half-width.** One run is an anecdote.
- **`Service` over `Seize`+`Release`** unless you need a span — the fused
  block cannot leak; the Sink refuses entities still holding units.
- **Traces are semantic events, not pixels** (`trace.jsonl`); the viewer
  tweens client-side. Turn tracing off (`trace_level="off"`) for statistics
  batches; animate one representative run.

## Repository layout

```
src/simulation_engine/
  blocks/            the block DSL — Tier 0 (Source/Queue/Delay/Service/…)
                     + Tier 1 (Batch/Unbatch, Gate, Move, TimeMeasure,
                     pool downtime, Fleet/Ride transporters)
  model.py           graph, validation, run loop, artifacts
  experiments.py     replications, sweeps, Monte Carlo, Welch
  theory_check.py    M/M/1 · M/M/c · M/G/1 · Kingman anchors + Little residual
  distributions.py   validated input distributions + nonstationary Poisson
  monitors.py        time-weighted & observation statistics
  viewer/            self-contained HTML replay viewer
skill/               the /simulate Claude Code skill (conversational workflow)
examples/            mm1_queue (theory anchor) · warehouse (batching,
                     breakdowns, forklifts, CRN sweep) · elevator (transporter
                     fleet, morning peak, capacity decision)
THEORY.md            the theoretical backbone (read it)
BACKLOG.md           out-of-scope roadmap: ABM, System Dynamics, optimization…
```

Every run emits three artifacts — `model.json` (graph + layout),
`trace.jsonl` (events), `kpis.json` (statistics) — and the viewer is a pure
function of them.

## The `/simulate` skill

`skill/SKILL.md` implements the conversational workflow (Robinson's
conceptual-modeling framework as the interview script; Law's 7 steps as the
spine): intake & triage → conceptual model Q&A → generate & validate →
showcase runs ("does this look right?") → replication sizing → scenario
comparison → deliverables. Install by symlinking into Claude Code:

```bash
ln -s "$(pwd)/skill" ~/.claude/skills/simulate
```

## Tests

```bash
uv run pytest
```

56 tests, including the ones that matter: simulated CIs must cover the exact
analytic values for M/M/1 and M/M/3; Little's residual stays under 2%; equal
seeds give byte-identical traces; every validation check catches its seeded
defect.

## License

MIT
