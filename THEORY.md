# The Theory Behind This Toolkit

This document is the theoretical backbone of `simulation-engine`. It exists for
two reasons: (a) so the toolkit's modeling framework follows established
simulation methodology rather than improvisation, and (b) so anyone reading
this repository can learn the theory the toolkit encodes. Every design rule in
the codebase traces back to a section here.

**Sources.** The content follows the canonical literature: Banks, Carson,
Nelson & Nicol, *Discrete-Event System Simulation*; Law, *Simulation Modeling
and Analysis* (and his WSC 2003/2009 tutorials); Robinson's conceptual-modeling
framework (JORS 2008, WSC 2013); Sargent's verification & validation tutorials
(WSC 2010); Hoad, Robinson & Davies on automated replication selection
(WSC 2007); Ross, *Simulation* and *Introduction to Probability Models*;
Kleinrock and Gross & Harris on queueing; Hopp & Spearman, *Factory Physics*.
Appendix D maps each text to the sections it grounds.

---

## Part 0 — Preface: what this toolkit is and is not

Simulation is **not optimization** and **not prediction**. A stochastic
simulation is a numerical experiment on a model: each run produces one *sample*
from a distribution of outcomes. The output of one run is one observation —
never "the answer."

Law's estimate is that model *programming* is only **25–50% of the work** of a
sound simulation study. The rest — problem formulation, conceptual modeling,
input modeling, validation, experiment design, output analysis — is what this
document covers. This toolkit makes the programming part conversational, which
lowers the barrier to *producing a model*. It does not lower the barrier to
producing a *correct* one; that is what the methodology in Part 2, the checks
in Part 6, and the analytic anchors in Part 7 are for. The methodology is not
negotiable just because the interface is a conversation.

---

## Part 1 — Taxonomy of models and simulation methods

### 1.1 Vocabulary (Banks)

A **system** is a collection of entities acting and interacting toward some
end; a **model** is a representation of a system built to study it. Inside a
model: an **entity** is an object of interest; **attributes** are its
properties; an **activity** is a time period of specified length; the **state**
is the set of variables needed to describe the system at any time; an
**event** is an instantaneous occurrence that may change state.

### 1.2 The three orthogonal axes

| Axis | Definition | Test question |
|---|---|---|
| **Static vs. dynamic** | Static: the passage of time plays no meaningful role. Dynamic: simulated time is essential to the model's structure. | Does the clock matter? |
| **Deterministic vs. stochastic** | Deterministic: all inputs fixed → one run gives the answer. Stochastic: inputs are draws from distributions → outputs are random variables that must be estimated statistically. | Is anything uncertain? |
| **Continuous vs. discrete** | Continuous: state changes continuously (ODEs). Discrete: state changes only at separated instants. | Does state jump or flow? |

### 1.3 Where the methods sit

| Method | Static/Dynamic | Det./Stoch. | Cont./Discrete | Unit of modeling |
|---|---|---|---|---|
| **Monte Carlo** | static | stochastic | — | a function of random inputs |
| **Discrete-event simulation (DES)** | dynamic | stochastic | discrete | entities contending for resources |
| **System dynamics** | dynamic | (usually) deterministic | continuous | stocks, flows, feedback loops |
| **Agent-based modeling** | dynamic | stochastic | discrete | autonomous heterogeneous agents |

This toolkit implements the first two. Parts 10.1–10.2 describe the other two
(roadmap).

Note a terminology conflict: Banks/Law use "Monte Carlo" narrowly for *static*
stochastic simulation; Ross and the physics/finance literature use it broadly
for any random-sampling computation, DES included. This document uses the
narrow sense.

### 1.4 Choosing the method — the triage question

- **Closed-form queueing** (Part 7) when the system reduces to a standard
  queue and a mean is all you need. Don't simulate what a formula answers.
- **Monte Carlo** when the question is "what is the distribution of an
  aggregate?" with no time-ordering, no queueing, no resource contention:
  cost rollups, project durations, risk sums.
- **DES** the moment entities *compete for limited resources* and waiting is
  part of the answer.

**When NOT to simulate** (Banks): the problem yields to common sense or a
closed form; direct experimentation is cheaper; the cost exceeds the value of
the answer; no data — not even estimates — exist; there is no time or money to
verify and validate; expectations cannot be managed; system behavior is too
complex to define. The toolkit's intake step asks these questions first.

---

## Part 2 — The methodology of a simulation study

This is the most important part of the document. The toolkit's conversational
workflow is these frameworks wearing a chat interface.

### 2.1 Banks' 12 steps (the reference diagram)

Four phases, with verification and validation as **decision gates with
backward arcs**, not linear steps:

- **Phase I — Discovery**: (1) problem formulation; (2) setting of objectives
  and overall project plan.
- **Phase II — Model building**: (3) model conceptualization; (4) data
  collection; (5) model translation (coding); (6) *verified?* — no → back
  to 5; (7) *validated?* — no → back to 3 and 4.
- **Phase III — Running**: (8) experimental design; (9) production runs and
  analysis; (10) *more runs?* — yes → back to 8.
- **Phase IV — Implementation**: (11) documentation and reporting;
  (12) implementation.

(Counts of "10" or "7" steps in other texts describe the same process at
different granularity — see §2.5.)

### 2.2 Law's 7 steps (the executable spine)

1. **Formulate the problem.** The kickoff must settle: overall objectives;
   **the specific questions to be answered** ("without such specificity, it is
   impossible to determine the appropriate level of model detail" — Law); the
   performance measures; scope; the configurations to be compared; time frame
   and resources.
2. **Collect information/data and build the conceptual model** (Law's
   "assumptions document"). No single person or document suffices; if a part
   of the system matters, query at least two subject-matter experts. The
   document contains: goals and issues; a process-flow diagram; bullet-level
   descriptions of each subsystem; **the simplifying assumptions and why they
   are safe**; limitations; input-data summaries. "There should not be a
   one-to-one correspondence between each element of the model and each
   element of the system. Start with a simple model and embellish it as
   needed."
3. **Is the conceptual model valid?** A **structured walk-through** of the
   document with all stakeholders, bullet by bullet, *before programming
   begins*. Law: this step "is very often skipped." Here it is mandatory.
4. **Program the model** (and verify/debug it).
5. **Is the programmed model valid?** Results validation against the real
   system's data where it exists — "the most important validation technique
   available" — plus face validity and sensitivity analysis.
6. **Design, conduct, and analyze experiments.** Decide run length, warm-up,
   and the number of independent replications. The named pitfall: one
   replication of arbitrary length treated as truth. **Construct a confidence
   interval.**
7. **Document and present the results** — including the conceptual model (it
   is the reusable artifact) and the validation evidence.

### 2.3 Law's 17 pitfalls (the anti-pattern checklist)

*Modeling & validation*: no well-defined objectives at the start;
management misunderstanding of what simulation is; failure to communicate with
the decision-maker regularly; failure to collect good system data;
**inappropriate level of model detail** ("one of the most common errors");
treating the study as primarily programming; lack of knowledge of methodology
and statistics.

*Software*: inappropriate software; **believing "easy-to-use" software requires
less technical competence** (directly relevant here: a conversational interface
does not either); blindly using software without understanding its assumptions;
**misuse of animation** — deciding from a short animation instead of
statistical analysis.

*Randomness*: **replacing an input distribution by its mean** (see §4.1 and
§7.5 — this single error erases queueing); normal or uniform distributions
where they "will rarely be correct"; **cavalier use of the triangular
distribution when data could be collected** (it cannot represent a long right
tail).

*Design & analysis*: treating output statistics as the true performance
measures; **no warm-up when steady-state behavior is of interest**; analyzing
correlated within-run output with formulas that assume independence
("variances might be grossly underestimated").

### 2.4 Robinson's conceptual-modeling framework (the Q&A spine)

**Definition** (Robinson): a conceptual model is *"a non-software-specific
description of the computer simulation model (that will be, is or has been
developed), describing the objectives, inputs, outputs, content, assumptions
and simplifications of the model."* It describes **the model**, not the real
world; it should drive the choice of tool, not be shaped by it; it persists
beyond the study; it is iterated, not written once.

**Four artifacts**, connected by knowledge acquisition → model abstraction →
design → coding: the *system description* (problem domain) → the *conceptual
model* (model domain) → the *model design* → the *computer model*. Robinson's
warning: *"a major failure in any simulation project is to try and model the
system description — everything that is known about the real system — and to
not attempt any form of model abstraction; this leads to overly complex
models."*

**Requirements of a good conceptual model**: validity (accurate enough *for
the purpose*), credibility (believed by the clients), feasibility (buildable
with the available data and time), utility (easy to use, quick to run).
Overarching: **build the simplest model that meets the objectives.** Simple
models are built faster, need less data, run faster, and their results can
actually be interpreted. The complexity–accuracy curve has diminishing returns
and *eventually turns down* — added complexity beyond your knowledge or data
forces incorrect assumptions.

**The five activities**, in order — objectives drive outputs, outputs drive
inputs, both drive content:

1. Understand the **problem situation**.
2. Determine the **modeling objectives** (and project objectives: time,
   budget, who must believe the result).
3. Identify the **outputs (responses)** — two kinds: statistics that show
   *whether* the objectives are achieved, and statistics that show *why not*.
4. Identify the **inputs (experimental factors)** — what can actually be
   changed, over what range.
5. Determine the **model content**: scope (what is in/out) and level of detail
   (how each in-scope component is represented) — plus the **assumptions**
   (made where knowledge is lacking) and **simplifications** (chosen for
   speed/transparency). These are different things; keep two registers.

**Abstraction levels**: *far abstraction* (heavily simplified — may be valid
yet lack credibility) vs *near abstraction* (close to the system description).
Sometimes detail is added purely for credibility; that is a legitimate reason.

**Methods of simplification** (Robinson 2004): aggregate components; exclude
components and details; replace components with random variables; exclude
infrequent events; reduce the rule set; split models.

### The mapping this toolkit implements

| Robinson activity | The question the toolkit asks | Artifact written |
|---|---|---|
| Problem situation | "What decision are you facing? What is going wrong?" | `conceptual-model.md` §1 |
| Objectives | "What must be true for this study to have been worth it? Who must believe the result? **How accurate does the answer need to be?**" | objectives table |
| Outputs / responses | "What number tells you the objective is met? What number tells you *why* it wasn't?" | responses table |
| Experimental factors | "What can you actually change, and over what range?" | factors table |
| Scope | "Which components are in? What is deliberately out?" | scope table |
| Level of detail | "For each in-scope component: how detailed, and why?" | detail table |
| Assumptions | "What don't we know that we will assume?" | assumptions register |
| Simplifications | "What do we know but choose not to model?" | simplifications register |

The accuracy question is Sargent's Step 2 (§6.4) and becomes `precision` in
the sequential replication policy (§5.4). The conversation ends with Law's
Step-3 structured walk-through: the tables are read back for approval before
any code is generated.

### 2.5 Terminology conflicts in the canon (flagged, resolved)

| Term | The conflict | This toolkit uses |
|---|---|---|
| "Conceptual model" | Robinson: describes the model (model domain). Sargent: a representation of the *problem entity*. Law: prefers "assumptions document." IS/SE: a solution-independent problem-domain description. | **Robinson's definition** |
| Steps in a study | Banks 12 / Law & Kelton 10 / Law 7 — same process, different granularity | Law's 7 as the flow; Banks' 12 as the reference diagram |
| Activity vs delay | Banks: *activity* = unconditional wait of known duration (scheduled on the event list); *delay* = conditional wait of unknown duration (never scheduled). Most texts blur this. | Banks' distinction |
| Terminating vs steady-state | Also called finite-horizon vs infinite-horizon (Rossetti) | terminating / steady-state |
| ρ and r | ρ = λ/(cμ) is *utilization*; r = λ/μ is *offered load* (Erlangs). Some texts call λ/μ "traffic intensity" in both cases. | Rossetti's convention: ρ = λ/(cμ), r = λ/μ |
| L = λW | Kleinrock writes N̄ = λT̄ — same law | L = λW |
| Warm-up | Also: transient period, initialization bias, truncation point; "burn-in" is the MCMC name | warm-up |
| Replication vocabulary | DES: replication/run. MC: sample/trial/iteration | *replication* for DES, *sample* for static MC |

---

## Part 3 — Discrete-event simulation fundamentals

### 3.1 The mechanism

State changes only at **events**. The engine keeps a **future event list
(FEL)** ordered by event time. The **next-event time-advance algorithm**:

1. Remove the imminent event (smallest time) from the FEL.
2. Advance the clock to that time.
3. Execute the event: update state, entity attributes, list memberships.
4. Generate any future events it implies and insert them into the FEL.
5. Update statistics.

Repeat until a stopping condition: a scheduled end time T_E, an event count,
or FEL exhaustion. Nothing happens between events — the clock jumps, which is
why DES is fast. **Bootstrapping**: each arrival, once processed, schedules
the next arrival by drawing an interarrival time.

A DES **snapshot** at time t contains the state, entity statuses, list
contents, the FEL, and the cumulative statistics — everything needed to
continue. Only one snapshot exists at a time.

### 3.2 The three worldviews

| Worldview | The modeler thinks in terms of | Historically |
|---|---|---|
| **Event scheduling** | events; one routine per event type | SIMSCRIPT |
| **Activity scanning** | activities and the *conditions* that let them begin; re-scan on every advance (slow); improved by the three-phase approach (B/C activities) | GSP |
| **Process interaction** | **processes** — "a time-sequenced list of events, activities and delays, including demands for resources, that define the life cycle of one entity"; processes interact by contending for resources | GPSS |

**This toolkit is process-interaction**: SimPy runs one generator per entity,
suspended at `timeout`/`request` events; the FEL still exists underneath
(SimPy's event heap). Model authors never see either — they declare a block
graph (Layer 2), and the generators live inside the block implementations.
The reason is empirical: LLM-written raw process code fails *silently* (a
missing `yield` runs and produces plausible wrong numbers), while a block
graph is validatable before it runs.

### 3.3 Resources, queues, disciplines

A **resource** is limited capacity that entities seize and release; a
**queue** is the ordered list of entities waiting for it. Disciplines: FIFO
(default), LIFO, SIRO, priority (preemptive or not), SPT/EDD. Behavioral
extensions: **balking** (refuse to join a full queue), **reneging** (abandon
after waiting too long), **jockeying** (switch queues).

A fact worth internalizing: for a work-conserving single-class queue, the
discipline does **not** change L, W, or utilization (Little's Law is
discipline-free) — it changes the *distribution* of waiting time: variance,
tails, fairness. If you only need means, discipline is irrelevant; the moment
you care about p95 wait, it is everything. That is a reason to simulate.

In this toolkit: resources are **identity-bearing** (`pool#3`, never an
anonymous slot) so the trace can say which server an entity was on and pools
report per-unit utilization; the preemption/resume policy is library-owned
(the residual-service accounting is a classic silent-error site).

---

## Part 4 — Input modeling

### 4.1 The cardinal sin

**Never replace an input distribution by its mean.** Queueing congestion is
driven by *variability*: the Kingman approximation (§7.5) makes waiting time
proportional to (c_a² + c_s²)/2 — the squared coefficients of variation of
interarrival and service times. Set variability to zero and the model predicts
zero waiting at any utilization below 1. Large values, even infrequent ones,
dominate time-in-system and maximum queue length. The mean is not the model.

Two corollaries (Law): the **normal** distribution is almost never right for a
duration (it always has positive probability of a negative value) and the
**uniform** rarely is; the **triangular** is a data-poverty fallback — it
cannot represent a long right tail, "a common situation in practice" — and its
use must be flagged in the assumptions register.

### 4.2 Choosing a family — from the physics of the process

| Distribution | Use for | Notes |
|---|---|---|
| Exponential | interarrival times of a Poisson stream; constant-hazard lifetimes | memoryless; cv = 1; rarely right for *service* times |
| Poisson | *counts* of arrivals in an interval | the discrete dual of exponential interarrivals |
| Erlang-k / Gamma | task times: sums of k phases | cv = 1/√k — "like exponential but steadier" |
| Lognormal | right-skewed durations; products of many effects | parameterize by the mean/sd of X, not of ln X (this toolkit's `Lognormal` does that for you) |
| Weibull | time to failure | shape <1 infant mortality, =1 exponential, >1 wear-out |
| Triangular | only min/mode/max available from an expert | flag it; no right tail |
| PERT (Beta) | expert-estimated activity durations | a smoothed triangular |
| Uniform | genuinely equally likely outcomes; last resort | |
| Empirical | resampling observed data | cannot extrapolate beyond observed min/max |

Heuristic: **pick the family from the mechanism, then fit the parameters.**
Count → Poisson; time between independent random events → exponential; sum of
phases → Erlang; product of effects → lognormal; hazard story → Weibull; three
numbers from a human → triangular/PERT, flagged.

The **coefficient of variation** cv = σ/μ is the single most diagnostic
number: cv ≈ 1 exponential-like, cv < 1 Erlang-like, cv > 1
hyperexponential/lognormal-like (and expect congestion trouble).

### 4.3 Fitting and testing

Process: plot the data first (histogram: √n or Sturges' ⌊1+log₂n⌋ bins;
time-series plot should be a patternless cloud; near-zero lag-1
autocorrelation — fitting IID distributions to autocorrelated data invalidates
everything downstream). Hypothesize families, estimate parameters (moments or
MLE), then check fit — χ² (needs ≥5 expected per class; interval-sensitive),
Kolmogorov–Smirnov (small samples; conservative with estimated parameters),
Anderson–Darling (tail-weighted — usually what you want), and always Q–Q/P–P
plots.

**The sample-size paradox**: GOF tests reject nothing with little data and
reject *everything* with lots of data. Use them as evidence, never as a gate;
decide fitness relative to the modeling objectives and the plots.

Special cases: **time-varying arrivals** need a nonstationary Poisson process
with rate function λ(t), sampled by *thinning* (this toolkit's
`RateSchedule`); before pooling "identical" machines' data, test homogeneity
(Kruskal–Wallis) — nominally identical equipment often isn't. **No data at
all?** Build the model with expert-estimated inputs, run a sensitivity screen
to find which inputs move the outputs, then spend collection effort only
there.

---

## Part 5 — Output analysis

### 5.1 Why one run is an anecdote

Within a run, observations are **autocorrelated** (lag-1 correlations ~0.9 in
queues), **non-stationary** (early observations depend on initial conditions),
and non-normal. Classical statistics on within-run data grossly underestimates
variance. The unit of analysis is the **replication**: n independent runs
differing only in random-number streams, each reduced to one summary value —
those n values are IID and ordinary statistics applies.

### 5.2 Terminating vs steady-state — the first question

- **Terminating**: a natural end exists (the shop closes empty; the batch
  completes). Initial conditions are *part of the model*. No warm-up.
- **Steady-state**: no natural end (a 24/7 line); interest is long-run
  behavior. Initial conditions are a *bias source* to remove.

Everything downstream differs, so the conceptual-model Q&A asks this
explicitly: "does this system reset, or does it run continuously?"

### 5.3 Confidence intervals

For replication summaries X₁…Xₙ:

    X̄ ± t(1−α/2, n−1) · s/√n        half-width h = t · s/√n

**Every KPI ships with its half-width — never a bare point estimate.** (This
toolkit's experiment layer enforces that; the Report tab shows CI columns
everywhere.)

### 5.4 How many replications

Three methods, in increasing quality: rule of thumb (≥3–5 — only good for
saying one run is unwise); the graphical method (plot the cumulative mean,
eyeball the flattening); and **the sequential precision procedure** (Hoad,
Robinson & Davies 2007), which this toolkit implements:

Define relative precision d_n = 100 · halfwidth/|mean|. Run a minimum (default
5), then add replications until d_n ≤ d_required — **and stays there for a
look-ahead window** f(kLimit) = kLimit (or n·kLimit/100 past n=100). The
look-ahead exists because a series can converge by luck and diverge again;
without it the procedure stops at n=3–4 when hundreds are needed. **kLimit = 5
is the empirically validated default** (with it, coverage of the true mean was
≥95% across all tested models; raising it to 10 or 25 changed bias by <0.3%).

Quick planning arithmetic: n ≥ n₀(h₀/h)² — to halve a half-width, quadruple
the replications. For a *relative* error target γ, aim at γ′ = γ/(1+γ) (the CI
is centered on the estimated, not true, mean — a routinely omitted
correction).

### 5.5 Warm-up (steady-state only)

Starting empty-and-idle biases congestion estimators *downward* (a worked
Rossetti example: −58% on mean queueing time from the first 20 customers).
Fix: delete data before a truncation point d, i.e. reset the statistics — not
the system state — at t = T_w.

**Welch's method** (the standard): make R ≥ 5 replications; average across
replications at each observation index (this kills noise but preserves the
transient); smooth with a centered moving average (window ≤ m/4); plot for
several windows and pick where the curve levels off. Different KPIs suggest
different d — **take the largest**. Rules of thumb: run length ≥ 10 × T_w;
deleting data trades bias down for variance up, so don't over-delete.

This toolkit ships Welch as an analysis helper (`welch_warmup`) that
recommends a truncation from the plateau crossing of the smoothed ensemble —
eyeball the curve before trusting the number; Welch is a graphical method.
(MSER-5 and automated procedures: backlog.)

**Replication–deletion** (n replications, each with the warm-up removed) is
this toolkit's default steady-state design. The alternative, **batch means**
(one long run split into 10–30 batches after deletion, lag-1 correlation
test), pays the warm-up once but composes poorly with experiments —
backlog.

### 5.6 Comparing alternatives

**Common random numbers (CRN)**: run scenario A and scenario B with identical
streams per stochastic source, pairing replication i across scenarios. Since

    Var(X̄_A − X̄_B) = Var(X̄_A) + Var(X̄_B) − 2·Cov(X̄_A, X̄_B),

the induced positive covariance shrinks the variance of the *difference* —
often by 2–3× on the half-width. Requirements: **dedicated named streams per
stochastic source** (one for arrivals, one per service, …), or a change in one
scenario desynchronizes everything. This toolkit's RNG design (per-name
`SeedSequence` streams) provides CRN automatically in `sweep(crn=True)`.

Analyze paired: D_i = X_i − Y_i, CI = D̄ ± t·s_D/√n. **Report the interval on
the difference, never a bare p-value** — and if the interval contains 0, say
"the data cannot distinguish these scenarios." That is a valid answer.

Other variance-reduction tools (antithetic variates, control variates) exist;
note that naively combining antithetics with CRN can *hurt* — don't stack them
blindly. For k > 2 alternatives: Bonferroni (α/(k−1) per comparison) is crude
but safe; indifference-zone selection and multiple-comparisons-with-the-best
are the proper machinery (backlog).

---

## Part 6 — Verification and validation

### 6.1 Four different things

- **Verification**: did we build the model *right*? (The code matches the
  conceptual model — debugging.)
- **Validation**: did we build the *right model*? (Accurate enough **for the
  particular objectives** — validity is always relative to a purpose.)
- **Credibility**: is the model *believed* by the decision-maker?
  **Validity does not imply credibility, and vice versa** — a technically
  sound model whose assumptions nobody understands goes unused; a credible
  model with an impressive animation may be junk (Law).
- **Accreditation**: official certification for a specific use (defense
  world; out of scope).

Sargent's economics: it is too costly to prove a model absolutely valid;
you test until *sufficient confidence for the intended use* is reached, and
passing many tests never guarantees validity everywhere.

### 6.2 Sargent's validation techniques (the toolkit's `validate` menu)

Animation · comparison to other models (→ Part 7, automated here) ·
**degenerate tests** (λ > cμ ⇒ the queue must grow without bound) · event
validity · **extreme-condition tests** (zero arrivals ⇒ W = service time;
c → ∞ ⇒ Wq → 0) · **face validity** (show the walk-through and the animation
to someone who knows the system) · historical data validation (build on part
of the data, test on the rest) · internal validity (replications: excessive
cross-replication variability questions the model *and* the system) ·
multistage validation · operational graphics · **parameter
variability/sensitivity analysis** (the same directions of change must occur
in the model as in reality; sensitive parameters must be made accurate) ·
predictive validation · **traces** (follow one entity through the logic —
this toolkit's `trace.jsonl` is exactly this, machine-readable) · Turing
tests (can experts tell model output from system output?).

### 6.3 Sargent's minimum procedure (adopted)

1. Agree the validation approach and techniques *before* building.
2. **Specify the required output accuracy up front** (this becomes the
   sequential policy's `precision`).
3. Test the assumptions and theories underlying the model where possible.
4. Face validity on the conceptual model in every iteration.
5. Explore the model's behavior in every iteration.
6. Compare model and system output for several conditions in at least the
   final iteration (when system data exists).
7. Write validation documentation (per-domain confidence: data validity /
   conceptual model / verification / operational validity).
8. If the model lives on, schedule periodic revalidation.

### 6.4 Two honest notes

On hypothesis tests for validation, Law's objection stands: the null "model
= system" is *known* to be false — the model is an approximation. The right
question is whether the differences are large enough to change the decision;
use CIs on differences, and judge the required accuracy against the decision
(a 3% error is fine when the decision is insensitive at 3%).

When the real system is **not observable** — new designs, hypothetical
configurations, which is often the whole point of simulating — high
statistical confidence in validity is *not attainable*. The honest posture is:
verify thoroughly, anchor on analytic references (Part 7), run degenerate and
extreme-condition tests, get face validity, and present results with that
caveat. A toolkit that always claims "validated" is lying.

---

## Part 7 — Queueing theory: the analytical sanity-check layer

Why this is here: closed-form queueing results are **exact** for simple
systems, so they anchor the simulation. Simplify the model to a standard
queue, check the simulated CIs cover the analytic values, then add realism.
This is Sargent's "comparison to other models," and this toolkit automates it
(`theory_check`): when a model reduces to M/M/1, M/M/c, or M/G/1, the analytic
values are computed and compared with the replication CIs — a CI that misses
an exact value means a bug before it means a finding.

### 7.1 Notation and the fundamental relations

Kendall notation **A/B/c/K/N/D**: interarrival distribution / service
distribution / servers / capacity / population / discipline (trailing fields
omitted when ∞, ∞, FCFS). M = exponential ("Markovian"), D = deterministic,
E_k = Erlang, G = general.

λ = arrival rate, μ = service rate per server, c = servers,
**r = λ/μ** (offered load), **ρ = λ/(cμ)** (utilization; stability needs ρ<1).

    L  = λW          (Little's Law)
    Lq = λWq
    W  = Wq + 1/μ
    L  = Lq + r

**Little's Law** is the most important relation in this document: it holds for
*any* stable system regardless of arrival process, service distribution, or
discipline — it only needs long-run averages, and it applies to any nested
subsystem. Two uses here: (a) **a runtime invariant** — every run computes L
(time-average WIP) and λ·W independently and reports the residual; a mismatch
is a statistics bug, a leak, or non-stationarity, never a finding; (b) sanity
arithmetic without any model at all (Factory Physics form:
WIP = throughput × cycle time).

### 7.2 The exact references

**M/M/1** (ρ = λ/μ):

    P_n = (1−ρ)ρⁿ      L = ρ/(1−ρ)       Lq = ρ²/(1−ρ)
    W = 1/(μ−λ)        Wq = ρ/(μ−λ)

**The ρ/(1−ρ) shape is the single most important intuition in queueing**: at
ρ=0.5, Lq=0.5; at ρ=0.8, Lq=3.2; at ρ=0.95, Lq=18; at ρ=0.99, Lq=98.
Congestion is *hyperbolic* in utilization. Capacity decisions made on average
utilization alone are catastrophically wrong near saturation.

**M/M/c**: with r = λ/μ, the probability an arrival waits is **Erlang-C**:

    C(c,r) = [ r^c / (c!(1−ρ)) ] · P₀,
    P₀ = [ Σ_{k=0}^{c−1} r^k/k!  +  r^c/(c!(1−ρ)) ]^{−1}

    Wq = C(c,r) / (cμ − λ)      W = Wq + 1/μ      Lq = λWq      L = Lq + r

Pooling corollary: one shared queue into c servers beats c separate queues at
the same total capacity — economies of scale against variability.

**M/G/1** (Pollaczek–Khinchine, exact for any service distribution with
variance σ²):

    Lq = (λ²σ² + ρ²) / (2(1−ρ))

Special cases teach the variability lever: deterministic service (σ=0) halves
Wq versus exponential.

### 7.3 The approximation that justifies the whole toolkit

**Kingman / VUT** for G/G/1:

    E[Wq] ≈ ( (c_a² + c_s²)/2 ) · ( ρ/(1−ρ) ) · τ
             ───────V───────     ────U────    T

Waiting = **V**ariability × **U**tilization × **T**ime (Factory Physics'
central equation; "generally very accurate near saturation"). Three readings:
congestion explodes as ρ→1; congestion is *linear in variability* — halve
(c_a²+c_s²)/2 and you halve the queue; and set variability to zero (use means)
and you predict no queue at all — §4.1's cardinal sin, quantified. Related
Factory Physics laws: increasing variability always degrades performance; and
variability *will* be buffered — by inventory, capacity, or time; you only
choose which.

For c > 1 with general service this toolkit uses the Allen–Cunneen-style
extension (Erlang-C base × variability factor) — labeled as an
**approximation** in reports, unlike the exact references above.

### 7.4 Where formulas run out — why DES exists

Finite buffers and blocking; balking/reneging; priorities with preemption;
resources with schedules, breaks, and failures; batching and assembly;
multi-class routing; non-stationary arrivals; networks with feedback;
transient (non-steady-state) questions; *distributions* of waiting rather than
means. Each of these breaks the closed forms — and each is a block or a
parameter in this toolkit.

---

## Part 8 — Monte Carlo methodology

### 8.1 Static Monte Carlo

The model is a function, not a process: Y = g(X₁,…,X_k) with random inputs.
Sample N times, report the **distribution** of Y — P10/P50/P90 and
P(Y > threshold) are usually the decision-relevant outputs, not the mean.

**The flaw of averages** (Jensen's inequality): for a project with parallel
paths, E[max(A,B)] > max(E[A],E[B]) — deterministic rollups built on
single-point estimates systematically understate durations and costs. This is
the static analogue of §4.1, and the first thing a Monte Carlo of a real
project shows.

Input **correlation matters and is usually ignored**: positively correlated
cost items make the total's tails fatter than independent sampling predicts
(fix: rank-correlation induction / copulas — backlog).

### 8.2 Convergence

The estimator's standard error is s/√N: **O(N^{−1/2}) convergence, independent
of dimension**. Halving the error quadruples the samples; one more decimal
digit costs 100×. Dimension-independence is why MC beats quadrature on
50-input models. Tail probabilities are harder than means: estimating a
probability p has relative error √((1−p)/(Np)) — rare events need enormous N
(importance sampling: backlog). Choose N with the same machinery as §5.4 —
this toolkit's `monte_carlo(precision=…)` runs the sequential rule on the
output's CI.

### 8.3 Random-variate generation

Pseudo-random numbers are a deterministic sequence statistically
indistinguishable from U(0,1) draws. **Streams** — independent sub-sequences
per named stochastic source — are the mechanism behind reproducibility and CRN;
this toolkit spawns one PCG64 generator per (seed, replication, source name)
via NumPy `SeedSequence`, so stream identity survives code reordering and
parallel execution.

Recipes: **inverse transform** X = F⁻¹(U) (exponential:
X = −ln(U)/λ; triangular and empirical by formula/table); **convolution**
(Erlang = sum of k exponentials); **acceptance–rejection** (normal, gamma,
beta); **thinning** for nonstationary Poisson: generate candidates at
λ_max and keep each with probability λ(t)/λ_max.

---

## Part 9 — Sensitivity analysis and choosing between alternatives

Three different activities share the name "sensitivity analysis":

1. **Robustness of a conclusion**: an expert guessed p = 0.75 — rerun at 0.70
   and 0.80 (with replications); if the recommendation stands, the guess is
   safe; if not, that input needs real data. Also applies to the *choice of
   distribution* and the *level of detail* — Sargent: the model must move in
   the same direction as the real system.
2. **Factor screening**: which inputs move the outputs at all? Do this early —
   it prioritizes data collection (§4.3's no-data strategy).
3. **Scenario comparison / decision analysis**: which configuration should we
   pick? CRN + paired CIs on differences (§5.6).

### The OFAT rule

Law, verbatim: it is *"not correct, in general, to vary one factor at a time
while setting the other factors at some arbitrary values (this dangerous
practice is sometimes called the one-factor-at-a-time approach)."* OFAT cannot
detect interactions — and congestion effects are strongly non-additive near
saturation (ρ/(1−ρ)), so DES models nearly always interact.

**Encoded in this toolkit**: OFAT sweeps are legitimate for single-factor
robustness checks and for screening, and reports label them as such; any claim
about *combinations* of factors requires the full grid (or a factorial
design — 2^k factorials and response surfaces are the proper machinery;
backlog). Rankings are never by point estimate: every comparison carries a CI
on the difference, and "the data cannot distinguish these options" is a
reported verdict.

---

## Part 10 — Roadmap: what this toolkit deliberately does not do (yet)

### 10.1 System dynamics (Forrester, Sterman, Meadows)

SD models aggregate behavior as **stocks** (accumulations — they give systems
inertia and memory), **flows** (rates filling and draining them), and
**feedback loops** — reinforcing loops amplify (growth, collapse); balancing
loops seek goals; **delays** in balancing loops desynchronize variables and
produce oscillation. Mathematically: coupled differential equations integrated
numerically — dynamic, continuous, usually deterministic, no individual
entities. Sterman's process (Business Dynamics): problem articulation →
**dynamic hypothesis** (causal-loop / stock-flow diagrams) → simulation model
→ testing → policy design. Forrester's *Industrial Dynamics* founded the field
and first demonstrated demand amplification up a supply chain (the
**bullwhip effect**). Meadows' **leverage points** hierarchy (parameters <
buffers < structure < delays < feedback strength < information flows < rules <
goals < paradigms) answers a question DES structurally cannot: *where to
intervene in a system*. Why deferred: SD needs an integrator and a stock/flow
DSL, not an event loop — a different engine and a different conversation, not
an extension of this one. (PySD exists as a Python base.)

### 10.2 Agent-based modeling (Macal & North)

An ABM is (1) a set of **agents** with attributes and behaviors, (2) their
**relationships and interaction topology**, (3) an **environment**. The
defining property is **autonomy** — agents act on local information without
central control; the distinguishing capabilities are **heterogeneity across a
population** and **emergence/self-organization** (Schelling's segregation
model: individually mild preferences → dramatic aggregate segregation, with no
empirical data in the model at all — the canonical far abstraction). ABM does
not require its own time-advance mechanism — it can run time-stepped or on a
DES scheduler — so **this engine can host ABM later without a rewrite**;
what's genuinely new is the agent/behavior/topology layer and
pattern-oriented validation. (ODD is the standard model-description protocol.)

### 10.3 Also on the backlog

Optimization & calibration (OptQuest-style search, Bayesian optimization over
metamodels — explicitly out of scope for v1); batch means; MSER-5 automated
warm-up; ranking & selection (indifference-zone, KN, OCBA); global sensitivity
(Sobol/Morris, SALib); correlated Monte Carlo inputs (Iman–Conover); 2nd-order
Monte Carlo (epistemic vs aleatory loops); importance sampling; live-streaming
viewer; richer material handling (true accumulating conveyors, cranes,
multi-level networks). See `BACKLOG.md`.

---

## Appendix A — Glossary

**Entity** an object flowing through the model · **attribute** a property of
an entity · **activity** an unconditional wait of known duration (scheduled on
the FEL) · **delay** a conditional wait of unknown duration (resolved by
system conditions) · **event** an instantaneous state change · **FEL** the
future event list · **replication** one independent run (unique streams) ·
**scenario** one parameter combination · **warm-up** the deleted initial
transient · **terminating / steady-state** natural end vs long-run behavior ·
**CRN** common random numbers across scenarios · **half-width** the ± of a
confidence interval · **ρ** utilization λ/(cμ) · **r** offered load λ/μ ·
**cv** coefficient of variation σ/μ · **conceptual model** (Robinson) the
non-software description of the model: objectives, inputs, outputs, content,
assumptions, simplifications · **verification / validation** built right /
built the right thing.

## Appendix B — Formula sheet

    Little            L = λW          Lq = λWq        W = Wq + 1/μ      L = Lq + r
    M/M/1             L = ρ/(1−ρ)     Lq = ρ²/(1−ρ)   W = 1/(μ−λ)       Wq = ρ/(μ−λ)
    Erlang-C          C(c,r) = r^c/(c!(1−ρ)) · P₀ ;   P₀ = [Σ_{k<c} r^k/k! + r^c/(c!(1−ρ))]⁻¹
    M/M/c             Wq = C(c,r)/(cμ−λ)
    M/G/1 (P–K)       Lq = (λ²σ² + ρ²)/(2(1−ρ))
    Kingman (G/G/1)   Wq ≈ ((c_a²+c_s²)/2) · (ρ/(1−ρ)) · τ
    CI                X̄ ± t(1−α/2, n−1)·s/√n
    Replications      n ≥ n₀ (h₀/h)²  ;  relative target γ → use γ′ = γ/(1+γ)
    Sequential        d_n = 100·h_n/|X̄_n| ≤ d_required, held for f(kLimit) look-ahead reps
    Welch             ensemble-average R≥5 reps → moving average (window ≤ m/4) → pick the knee ; run ≥ 10·T_w
    Monte Carlo       SE = s/√N  (halve error ⇒ 4× N) ;  P(event) needs N ≫ 1/p
    CRN               Var(Δ) = Var_A + Var_B − 2Cov ;  paired CI on D_i = X_i − Y_i

## Appendix C — Checklists

**Banks: don't simulate when** — common sense or a closed form answers it;
direct experimentation is cheaper; cost exceeds savings; no data or estimates;
no time/money for V&V; unmanageable expectations; behavior too complex to
define.

**Law's 17 pitfalls** — §2.3 (use as a pre-flight checklist on every study).

**Robinson's conceptual-model tables** — objectives · responses ·
experimental factors · scope · level of detail · assumptions ·
simplifications (+ a process-flow diagram) — §2.4.

**Sargent's 15 validation techniques** — §6.2; **8-step minimum procedure** —
§6.3.

**This toolkit's automatic checks** — pre-run: unconnected ports, unreachable
blocks, Seize without reachable Release, impossible distribution parameters,
unstoppable runs. Runtime: entity balance (created = disposed + dropped +
in-system), Sink refuses entities holding resource units, Little's Law
residual. Post-run: analytic CI coverage when the model reduces to a known
queue.

## Appendix D — Annotated bibliography

Franco's full canon, mapped to this document. Titles beyond v1 scope carry
their roadmap note rather than being dropped.

| Text | Grounds |
|---|---|
| Banks, Carson, Nelson & Nicol — *Discrete-Event System Simulation* | Parts 1, 2.1, 3; when-not-to-simulate |
| Law — *Simulation Modeling and Analysis* + WSC 2003/2009 tutorials | Parts 2.2–2.3, 4, 5, 6, 9 |
| Robinson — *Simulation: The Practice of Model Development and Use*; JORS 2008 I/II; WSC 2013 | Part 2.4 — the toolkit's entire Q&A flow |
| Sargent — WSC 2010 V&V tutorial | Part 6 |
| Hoad, Robinson & Davies — WSC 2007 / JORS 2010 | §5.4 (implemented in `experiments.SequentialPolicy`) |
| Ross — *Simulation*; *Introduction to Probability Models* | Part 8; the probability underpinning Part 4 |
| Kleinrock — *Queueing Systems*; Gross et al. — *Fundamentals of Queueing Theory* | Part 7 |
| Hillier & Lieberman — *Introduction to Operations Research*; Taha; Winston | OR framing; queueing chapters → Part 7; LP/IP/DP chapters → optimization backlog |
| Hopp & Spearman — *Factory Physics* | §7.3 VUT and the variability laws; manufacturing applications for M2 examples |
| Forrester — *Industrial Dynamics*, *Urban/World Dynamics*; Sterman — *Business Dynamics*; Meadows — *Thinking in Systems*; Senge — *The Fifth Discipline* | Part 10.1 (System Dynamics roadmap) |
| Macal & North — *Tutorial on agent-based modelling* (JoS 2010) | Part 10.2 (ABM roadmap) |
| Boyd & Vandenberghe — *Convex Optimization*; Bertsekas — *Nonlinear Programming*, *DP & Optimal Control*; Nocedal & Wright; Bazaraa | Optimization backlog (out of scope v1 by design) |
| Chopra & Meindl — *Supply Chain Management*; Nahmias — *Production and Operations Analysis* | Application domains; bullwhip (Part 10.1) |
| Maynard's *Industrial Engineering Handbook*; Niebel's *Methods, Standards & Work Design*; Tompkins — *Facilities Planning* | Input modeling context (time standards) and layout problems for future examples |
| Gordon — *System Simulation*; Banks — historical foundations | Part 3 worldviews |
| Franklin/Powell/Emami-Naeini; Ogata — control theory | Continuous/dynamic modeling background for the SD backlog |
