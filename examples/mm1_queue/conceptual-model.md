# Conceptual model — M/M/1 queue

## 1 · Problem situation
A single server fed by Poisson arrivals — the canonical queueing system.
Customers arrive at rate λ, wait in an unbounded FIFO queue, receive
exponentially distributed service at rate μ, and leave. This example exists
to *validate the toolkit*: every KPI has an exact analytic answer.

## 2 · Objectives
| | |
|---|---|
| Organisational aim | none — validation anchor |
| Modeling objective | confirm simulated CIs cover the exact M/M/1 values |
| Required accuracy (primary KPI) | 95% CI must contain the analytic value |
| Audience / credibility needs | toolkit users reading the code |
| Study constraints | none |

## 3 · Outputs (responses)
| KPI | Type | Determines |
|---|---|---|
| time in system W | mean | matches 1/(μ−λ) = 5 min |
| queue wait Wq | mean | matches ρ/(μ−λ) = 4 min |
| entities in system L | time-avg mean | matches ρ/(1−ρ) = 4 |
| server utilization ρ | fraction | matches λ/μ = 0.8 |

## 4 · Experimental factors (inputs)
| Factor | Range / values | Expected direction of effect |
|---|---|---|
| `lam` — arrival rate | 0.05 – 0.95 per min | ↑λ → congestion explodes as ρ→1 |
| `mu` — service rate | 0.5 – 2.0 per min | ↑μ → all waits fall |

## 5 · Scope
| Component | In / out | Justification |
|---|---|---|
| arrivals, queue, server, departures | in | the whole system |
| balking / reneging | **out** | M/M/1 assumes infinite patience |

## 6 · Level of detail
| Component | Representation | Why sufficient |
|---|---|---|
| arrivals | Poisson at rate λ (stationary) | definition of the M/M/1 |
| service | Service, c=1, duration ~ Exponential(rate=μ) | definition |
| queue | unbounded FIFO | definition |

## 7 · Run design
| | |
|---|---|
| Terminating or steady-state | steady-state |
| Horizon / stopping rule | 20,000 min per replication, n=20 |
| Warm-up | 2,000 min (empty-and-idle bias removal) |
| Base time unit | minutes |

## 8 · Assumptions (limited knowledge)
| # | Assumption | Basis | Risk if wrong |
|---|---|---|---|
| A1 | none — all inputs are definitional | — | — |

## 9 · Simplifications (deliberate omissions)
| # | Simplification | Why safe |
|---|---|---|
| S1 | none | the model *is* the reference |
