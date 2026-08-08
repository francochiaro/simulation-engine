# Conceptual model — <system name>

<!-- Robinson's framework (THEORY.md §2.4). Fill every section; "none" is an
     acceptable entry, an empty section is not. This document outlives the
     study — it IS the model, the code is an implementation. -->

## 1 · Problem situation
One paragraph: the system, what flows, what it competes for, what hurts.

## 2 · Objectives
| | |
|---|---|
| Organisational aim | … |
| Modeling objective | decide/estimate … to ±… by … |
| Required accuracy (primary KPI) | ±… (→ replication precision) |
| Audience / credibility needs | … |
| Study constraints | time / budget |

## 3 · Outputs (responses)
| KPI | Type (mean / percentile / probability) | Determines |
|---|---|---|
| … | … | achievement of objective |
| … | … | reason for failure |

## 4 · Experimental factors (inputs)
| Factor | Range / values | Expected direction of effect |
|---|---|---|
| … | … | … |

## 5 · Scope
| Component | In / out | Justification |
|---|---|---|
| … | in | … |
| … | **out** | doesn't touch the KPIs because … |

## 6 · Level of detail
| Component | Representation | Why sufficient |
|---|---|---|
| arrivals | Poisson at rate λ / RateSchedule / trace | … |
| … | Service, c=…, duration ~ Dist(…) | … |

## 7 · Run design
| | |
|---|---|
| Terminating or steady-state | … |
| Horizon / stopping rule | … |
| Warm-up (steady-state only) | from Welch on pilot reps |
| Base time unit | … |

## 8 · Assumptions (limited knowledge)
| # | Assumption | Basis | Risk if wrong |
|---|---|---|---|
| A1 | service time ~ Triangular(a,m,b) — expert estimate, no data | interview | tails understated → congestion optimistic |

## 9 · Simplifications (deliberate omissions)
| # | Simplification | Why safe |
|---|---|---|
| S1 | … | … |

## Walk-through record
Approved by <user>, <date>. Changes requested: …
