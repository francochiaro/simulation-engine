# Validation menu (Sargent's techniques, with runnable recipes)

Minimum for every study (Sargent's procedure, THEORY §6.3): accuracy agreed
up front · face validity each iteration · behavior exploration each
iteration · results comparison where system data exists · outcomes recorded
in `report.md` with per-domain confidence (data / conceptual / code /
operational: low·medium·high).

## Always run (automated by the toolkit)
- **Entity balance** — `kpis["entities"]["balance_ok"]` must be true.
- **Little's Law residual** — `kpis["little"]["residual_rel"] < 0.05`; a miss
  is a bug (leak, stats error, non-stationarity), never a finding.
- **Pre-run graph checks** — raised by `m.run()`.

## Comparison to other models (theory anchors)
```python
reps = replicate(make_model, n=20, until=..., warmup=..., seed=...)
chk = theory_check.check(make_model(), reps)   # None if no known reduction
```
If the real model doesn't reduce, **build a simplified copy that does**
(exponential everything, no balking) and check *that* — then re-add realism
and use Kingman's direction (more variability ⇒ more waiting) as the sanity
rail. Exact references must be covered by the CIs; approximations
(Kingman/Allen–Cunneen) should be near, and the report labels them.

## Degenerate tests
```python
m = make_model(arrival_rate=1.2 * total_service_rate)   # overload
```
Queue length must grow without bound (check the queue-length chart climbs
linearly). Starvation: λ→0 ⇒ W → mean service time exactly.

## Extreme-condition tests
Capacity → very large ⇒ Wq → 0 and utilization → λ/(cμ). Zero WIP at t=0 with
no arrivals ⇒ zero output. One entity alone ⇒ its time in system = sum of its
service times (trace it in the viewer).

## Face validity (the user is the expert)
Showcase run + viewer link: "watch the flow — where does it differ from the
real system?" Also: show utilizations — an expert knows whether packers are
~60% or ~95% busy. Disagreement = model bug OR system insight; find out which.

## Traces
`trace.jsonl` is machine-readable: pick one entity id, extract its events,
narrate its journey to the user ("order #42 arrived 09:12, waited 4 min…").
Catches routing/logic errors nothing else does.

## Historical / results validation (when data exists)
Feed a recorded day's arrivals via `Source(arrival_times=[...])`; compare
model output CIs to the recorded KPIs. Law: judge the difference against the
decision, not against zero — model ≠ system is already known.

## Sensitivity as validation
Vary an uncertain assumption (±: the A-register rows with high risk); if the
recommendation flips within the plausible range, the assumption needs data
before the study can conclude (THEORY §9.1).

## Internal validity
Cross-replication spread: if scenario CIs are so wide the answer flips run to
run at realistic n, the system itself is high-variance — report that as a
finding about the system, not a modeling failure.
