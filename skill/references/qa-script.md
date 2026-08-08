# The conceptual-model interview (Robinson's five activities)

Ask in this order — objectives drive outputs, outputs drive inputs, both
drive content. Don't fire all questions at once; 2–3 per message,
plain language, no jargon. Push back on vagueness: "improve the warehouse" is
not an objective; "decide whether 3 packers suffice for 600 orders/day at
< 20 min p95 dispatch time" is.

## 1 · Problem situation
- "Describe the system as if walking me through it. What flows through it
  (orders, people, pallets)? What does it compete for (staff, machines,
  space)?"
- "What decision are you trying to make, or what is going wrong?"

## 2 · Objectives
- "What must be true for this study to have been worth doing?"
- "Who has to believe the result?" (drives credibility → level of detail)
- **"How accurate does the answer need to be — ±what would change your
  decision?"** → `SequentialPolicy.precision`
- "Any deadline or budget on the study itself?"

## 3 · Outputs (responses)
- "What number tells you the objective is met?" (the primary KPI)
- "If it isn't met, what numbers would tell you *why*?" (utilizations, queue
  lengths, balk/renege counts)
- For each KPI: mean, or a percentile/probability? (p95 wait and P(wait>x)
  need distributions — say so in the report)

## 4 · Experimental factors (inputs)
- "What can you actually change? Over what range?" (staffing 2–5, buffer
  10–50…)
- "Which single factor matters most, if you had to guess?" (orders the sweep)

## 5 · Content — scope & level of detail
- "Walk me through one entity's journey, step by step." (becomes the block
  chain)
- Per step: "does it wait there? for what? how many can be served at once?"
- "What happens at the edges — full queue (balk?), long wait (leave?),
  breakdowns, shift changes?"
- Scope cuts: "I propose we leave out X because it doesn't touch the KPIs —
  agree?" (record as simplification)

## Mandatory classifiers
- **Terminating or steady-state**: "does the system empty and reset (a shop
  day), or run continuously?" — decides warm-up and run design (THEORY §5.2).
- **Time-varying arrivals**: "is demand flat, or peaky (lunch rush)?" — peaky
  ⇒ `RateSchedule` (nonstationary Poisson), NOT an average rate.

## Input data, per stochastic quantity
- "Do you have data (even 20 timestamps), or estimates?"
- Data → fit family from the mechanism (THEORY §4.2), sanity-check cv.
- Estimates → "give me min / typical / max" → `Triangular`/`Pert`, **record in
  the assumptions register** with the note that long tails are understated.
- Someone offers a single number → rule 4: ask for spread; never a bare mean.

## Close — the structured walk-through (Law step 3)
Read back every table in `conceptual-model.md`, bullet by bullet. "Anything
wrong or missing? At the right level of detail?" Only on explicit approval,
write code.
