# Backlog — future iterations

Out-of-scope-by-design for v1, recorded here so nothing is lost. Ordered
roughly by expected value. THEORY.md Part 10 carries the theory grounding for
the big three.

## Modeling paradigms (the big three, deliberately excluded from v1)

- **Agent-based simulation** (Macal & North; ODD protocol). Autonomy,
  heterogeneity, emergence. The DES engine can host ABM — an agent layer
  (behaviors, interaction topology, environment) on the same scheduler — so
  this is an extension, not a rewrite. Validation is pattern-oriented
  (Schelling as the canonical example). Candidate v2 flagship.
- **System dynamics** (Forrester, Sterman, Meadows). Stocks/flows/feedback,
  numerical integration, leverage-points analysis. A different engine
  (integrator + stock/flow DSL, PySD as a base) and a different Q&A script
  (dynamic hypothesis, causal-loop diagrams). Answers "where to intervene,"
  which DES cannot.
- **Optimization & calibration** (Hillier & Lieberman; Boyd & Vandenberghe;
  Bertsekas; Nocedal & Wright). Search over parameter space against simulated
  objectives (OptQuest-style metaheuristics, Bayesian optimization over
  metamodels), and calibration (fit parameters to observed data). Explicitly
  out of v1: the toolkit measures, it does not optimize.

## Engine / blocks (Tier 1 → Tier 2)

- Tier 1 completion beyond M2: multi-unit seize (n units per entity,
  deadlock-safe), preemption + failure/downtime with the resume-policy enum
  (preempt-resume vs preempt-restart), shift schedules / time-varying
  capacity, Batch/Unbatch, Split/Match/Assembler, Hold/Gate, RestrictedArea
  (WIP caps / CONWIP), TimeMeasure pairs, Storage/Retrieve, simplified
  accumulating Conveyor, Transporter (forklifts, AGVs, elevators).
- Tier 2: Pickup/Dropoff onto carriers, ResourceAttach/Detach (escorts),
  cranes/robots, true conveyor accumulation with spacing, multi-level
  networks, hierarchical sub-models (Enter/Exit ports).
- Custom-process escape hatch (`CustomProcess` block) with loud documentation.

## Statistics / experiments

- Batch means (single long run; Schmeiser 10–30 batches; lag-1 test) as an
  alternative to replication–deletion.
- MSER-5 and automated Welch for warm-up detection.
- Ranking & selection: indifference-zone (Rinott), KN/KN++, OCBA; subset
  selection ("possible best" vs "rejects", Simio-style).
- Factorial designs (2^k, fractional) and response surfaces; global
  sensitivity (Sobol, Morris — SALib).
- Correlated Monte Carlo inputs (Iman–Conover rank correlation, copulas).
- Second-order Monte Carlo (epistemic outer loop × aleatory inner loop).
- Importance sampling / rare-event estimation.
- Antithetic variates and control variates (with the CRN-interaction caveat).

## Viewer / UX

- Live-streaming mode: simulation in a subprocess, WebSocket/poll diffs,
  PixiJS/WebGL rendering (casymda architecture) — the trace emitter already
  supports streaming; only the transport is missing.
- Path/geometry layer: entities moving along drawn paths (conveyor lines,
  elevator shafts) instead of straight-line tweens; asset/sprite packs for
  warehouse/port/factory scenes.
- Process-map view auto-derived from the trace (directly-follows graph).
- Per-entity timeline inspector (click an entity, see its journey).
- Table view + texture fills for the accessibility pass.

## Ecosystem

- Text2Sim MCP interop (JSON schema import/export of models).
- Trace/KPI export to pandas/parquet helpers.
- A benchmark suite of NL system descriptions → expected model shapes (eval
  harness for the skill itself).

## Reading list backing future work

Sterman (Business Dynamics) and Forrester (Industrial Dynamics) for SD;
Macal & North for ABM; Hillier & Lieberman, Taha, Winston for OR breadth;
Boyd & Vandenberghe, Bertsekas, Nocedal & Wright, Bazaraa for optimization;
Chopra & Meindl and Nahmias for supply-chain applications; Hopp & Spearman
for factory-physics examples; Maynard's and Niebel's for work measurement;
Tompkins for facilities; Kleinrock and Gross et al. for deeper queueing;
Franklin/Powell and Ogata for the control-theory background of SD.
