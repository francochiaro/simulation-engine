---
name: simulate
description: Build and run a discrete-event or Monte Carlo simulation conversationally — conceptual model via Q&A, validated block-DSL model on the simulation-engine toolkit, replications with confidence intervals, scenario comparison, and a self-contained animated viewer. Trigger on /simulate, or when the user wants to simulate a system (warehouse, production line, service counter, elevator bank, port, call center), asks "what would happen if" about a queueing/capacity/flow question, wants a Monte Carlo of costs/durations/risk, or asks to model a process with waiting lines and limited resources.
---

# /simulate — agent-driven simulation studies

**Engine repo**: `~/dev/simulation-engine` (this skill lives inside it —
`skill/`). Read `THEORY.md` there for anything methodological; every rule
below cites it.

**Working dir**: `<cwd>/simulations/<model-slug>/` — holds
`conceptual-model.md`, `model.py`, `runs/<name>/` (artifacts + `index.html`
viewer), `report.md`. Never write into the engine repo itself.

**Run scripts with the engine's venv**:

```bash
uv run --project ~/dev/simulation-engine python simulations/<slug>/model.py
```

## Hard rules

1. **Methodology is not negotiable.** The workflow below is Law's 7 steps +
   Robinson's conceptual modeling (THEORY.md Part 2). Do not skip the
   walk-through, the validation passes, or the CI machinery because the user
   is in a hurry — say what you're skipping and what it costs.
2. **The user writes no code and sees no SimPy.** All models are Layer-2
   block DSL (`Source/Queue/Delay/Service/ResourcePool/Route/Assign/Sink`).
3. **Never report a KPI without its confidence interval.** One run is an
   anecdote. Rankings report CIs on *differences*; "the data cannot
   distinguish these options" is a valid verdict — deliver it when true.
4. **Never replace a distribution by its mean** (THEORY.md §4.1). If the user
   gives one number, ask for spread (min/mode/max → Triangular or Pert) and
   record the guess in the assumptions register.
5. **OFAT rule** (§9): one-factor sweeps are for robustness/screening only;
   label them so. Claims about factor *combinations* need the full grid.
6. **Don't simulate what a formula answers** — if the system reduces to
   M/M/c and the user needs a mean, compute it (`theory_check.mmc`) and say
   so. Simulate when distributions, behaviors (balk/renege), schedules, or
   networks break the closed forms.
7. **Animation is a validation aid, not evidence** (Law's pitfall). Decisions
   come from the replication statistics.

## Pipeline

### 1 — Intake & triage
Get the high-level description. Classify: DES / static Monte Carlo / closed
form (THEORY.md §1.4, when-NOT-to-simulate list). State the classification
and why in one paragraph. Genuinely unclear cases: ask.

### 2 — Conceptual model via Q&A
Interview per `references/qa-script.md` (Robinson's five activities, in
order — objectives → responses → factors → scope/detail → assumptions/
simplifications). Two questions are mandatory: **terminating or
steady-state?** ("does the system reset — a shop day — or run continuously?")
and **required accuracy** ("±how much would change your decision?" → becomes
the sequential policy's `precision`). Fill
`references/conceptual-model-template.md` → write `conceptual-model.md`.
**End with the structured walk-through**: read the tables back; get explicit
approval before generating code.

### 3 — Build
Write `model.py`: a `make_model(**factors)` factory (experimental factors as
keyword args — that's what `sweep()` varies), `m.output(...)` for the
response KPIs, `if __name__ == "__main__"` showcase block. Block positions
`.at(x, y)` roughly following the physical layout. `m.run()` validates the
graph automatically; fix anything it raises.

### 4 — Validation passes (before any production numbers)
- **Showcase run**: short horizon, full trace → `build_viewer` → give the
  user the `index.html` path: *"open this and watch — does the flow look like
  your system?"*
- **theory_check**: if the model (or a simplified copy) reduces to
  M/M/1/M/M/c/M/G/1, run `replicate` + `theory_check.check` — CIs must cover.
- **Degenerate + extreme tests** (menu + recipes in
  `references/validation-menu.md`): overload (λ > cμ ⇒ queue grows without
  bound), starve (λ→0 ⇒ W → service time), capacity → ∞ ⇒ Wq → 0.
- Check the run report: entity balance ✓, Little residual < 5%.
- Iterate with the user until face-valid. Record outcomes in `report.md`.

### 5 — Replication sizing
Terminating: replicate the natural horizon. Steady-state: pick warm-up with
`welch_warmup` on ≥5 pilot reps (show the curve; T_end ≥ 10×warmup). Then
`SequentialPolicy(kpi=<primary response>, precision=<from step 2>)`. Report
recommended n and achieved precision; let the user trade precision vs runtime.

### 6 — Parameter variation
`sweep()` over the experimental-factor values from the conceptual model
(explicit scenario list or grid; CRN on). Present: per-scenario table
(mean ± CI), differences vs baseline with paired CIs, verdict per comparison.
Never rank on point estimates.

### 7 — Deliver
`build_viewer(showcase_run, out_dir=..., experiment={kind, n_replications,
kpi_table, theory_check, scenarios: {kpi, table, compare}, sequential})` →
surface the path. Write `report.md`: question, conceptual model summary,
validation evidence, results with CIs, sensitivity verdicts, assumptions +
simplifications registers, and what would sharpen the answer (data to
collect — §4.3 no-data strategy).

## Gotchas (hard-won)

- `Service(resource=n)` creates a dedicated pool `<name>.servers`; pass a
  `ResourcePool` object to *share* servers between blocks.
- Multi-unit seize per entity is not in v1 — model "needs 2 workers" as one
  unit of a half-capacity pool, or chain Seize blocks knowing they can
  deadlock (BACKLOG.md).
- A `Queue` before a `Service` reserves servers slot-based, so **discipline
  lives in the Queue** (priority there, not entity.priority at the pool).
- Unconnected `balk`/`timeout` ports **drop** entities (counted, traced,
  never silent) — connect them to a Sink when lost demand is a KPI.
- Long stats runs: `trace_level="off"` (default in `replicate`), animate a
  short showcase separately. The viewer refuses traces > 200k events.
- `until=` is in the model's base time unit; `m.u.hours(8)` converts.
- Warm-up resets statistics, not state; time-in-system for entities straddling
  the boundary includes pre-warmup time (standard replication–deletion
  caveat).
- Seeds: fixed seed = reproducible; vary `replication`, not `seed`, for
  independent replications (streams derive from both).

## References

| File | When |
|---|---|
| `references/qa-script.md` | Step 2 — the interview, question by question |
| `references/conceptual-model-template.md` | Step 2 — the artifact to fill |
| `references/validation-menu.md` | Step 4 — Sargent's techniques + runnable recipes |
| `references/pitfalls.md` | Pre-flight checklist (Law's 17) — skim before step 3 |
| `~/dev/simulation-engine/THEORY.md` | The why behind every rule |
| `~/dev/simulation-engine/examples/mm1_queue/run.py` | Canonical end-to-end shape |
