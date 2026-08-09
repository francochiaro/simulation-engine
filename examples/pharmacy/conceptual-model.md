# Conceptual model — pharmacy counters

## 1 · Problem situation
A retail pharmacy with 2 service counters and a single shared FIFO line.
Walk-in customers arrive through the day with a strong lunch-hour rush;
customers who wait too long give up and leave (lost sales, bad experience).
The owner is considering adding a third counter.

## 2 · Objectives
| | |
|---|---|
| Organisational aim | stop losing lunch-hour customers without overstaffing |
| Modeling objective | decide whether a third counter is worth it: estimate customers lost/day and waiting times for 2 vs 3 counters |
| Required accuracy (primary KPI) | ±10% relative on customers lost/day (tighter would not change the decision) |
| Audience / credibility needs | the pharmacy owner |
| Study constraints | none |

## 3 · Outputs (responses)
| KPI | Type | Determines |
|---|---|---|
| `customers_lost` | count per day | the objective — lost demand |
| `wait_mean_min` | mean (min) | experience of those who stay |
| `wait_p95_min` | 95th percentile (min) | the lunch-peak experience the mean hides |
| `customers_served` | count per day | throughput |
| counter utilization | fraction | overstaffing check (the cost side) |

## 4 · Experimental factors (inputs)
| Factor | Range / values | Expected direction of effect |
|---|---|---|
| `n_counters` | 2 – 4 | ↑counters → fewer lost, lower utilization |
| `peak_rate` | 0.6 – 1.2 /min | ↑peak → losses explode at 2 counters |
| `service_time` | distribution (default Lognormal(4, 2.5) min) | ↑mean/cv → more waiting (Kingman) |
| `patience` | distribution (default Pert(2, 6, 15) min) | ↓patience → more walkouts |

## 5 · Scope
| Component | In / out | Justification |
|---|---|---|
| walk-in customers, single line, counters | in | the whole decision |
| prescription prep in the back office | **out** | folded into service-time spread |
| phone orders / deliveries | **out** | don't compete for counters |
| staff breaks / shift changes | **out** | counters assumed staffed all day |

## 6 · Level of detail
| Component | Representation | Why sufficient |
|---|---|---|
| arrivals | RateSchedule (nonstationary Poisson): 0.30/min from open, 0.90/min 12:00–14:00, 0.35/min afternoon, 0.55/min 18:00–20:00, 0.25/min last hour | the lunch peak IS the problem — an average rate would hide it (cardinal sin, THEORY §4.1) |
| line | single shared FIFO queue | how the shop actually queues |
| impatience | renege after Pert(2, 6, 15) min → walked_out sink | the loss mechanism; per-customer patience |
| service | Service, c=`n_counters`, duration ~ Lognormal(mean=4, sd=2.5) min | right-skewed (occasional complex prescriptions) |

## 7 · Run design
| | |
|---|---|
| Terminating or steady-state | terminating — a 12 h shop day (09:00–21:00), opens empty |
| Horizon / stopping rule | 720 min; replications sized by SequentialPolicy(customers_lost, 10%) |
| Warm-up | none (opens empty by design) |
| Base time unit | minutes |

## 8 · Assumptions (limited knowledge)
| # | Assumption | Basis | Risk if wrong |
|---|---|---|---|
| A1 | arrival profile (0.30 / **0.90 lunch** / 0.35 / 0.55 / 0.25 per min) | owner's description, no till data | peak height drives everything; ±20% shifts losses strongly |
| A2 | service ~ Lognormal(4, 2.5) min | estimate — "a few minutes, sometimes much longer"; no data | long tail understated → waiting optimistic |
| A3 | patience ~ Pert(2, 6, 15) min | estimate — nobody measured walkouts | primary KPI scales with it |
| A4 | ±10% relative accuracy suffices | decision threshold, not measurement | more replications if tightened |

## 9 · Simplifications (deliberate omissions)
| # | Simplification | Why safe |
|---|---|---|
| S1 | one customer class (no priority / pickup-vs-consult split) | both classes share counters and line; split doesn't change the counter count decision |
| S2 | counters identical and always staffed | matches how the owner runs the shop |
| S3 | no balking at the door | the observed behavior is join-then-leave, which reneging captures |
