# Conceptual model — elevator bank

## 1 · Problem situation
A 20-floor tower served by a 2-car service elevator bank. During the morning
up-peak most riders go lobby → upper floors while a background trickle moves
between floors. Riders complain about waiting for a car.

## 2 · Objectives
| | |
|---|---|
| Organisational aim | decide whether a third car is worth it |
| Modeling objective | estimate p95 wait-for-car for 2 vs 3 cars |
| Required accuracy (primary KPI) | CI on the 2-vs-3 difference excluding 0 (or a "cannot distinguish" verdict) |
| Audience / credibility needs | building ops |
| Study constraints | none |

## 3 · Outputs (responses)
| KPI | Type | Determines |
|---|---|---|
| `wait_p95_s` | 95th percentile (s) | rider experience — the mean hides the peak |
| `wait_mean_s` | mean (s) | context |
| `door_to_door_mean_s` | mean (s) | total trip |
| car utilization | fraction | idle capacity |

## 4 · Experimental factors (inputs)
| Factor | Range / values | Expected direction of effect |
|---|---|---|
| `n_cars` | 1 – 6 | ↑cars → p95 wait falls, utilization falls |

## 5 · Scope
| Component | In / out | Justification |
|---|---|---|
| lobby up-peak + interfloor trickle | in | the demand |
| freight/goods traffic | **out** | separate shaft |
| direction batching / group control | **out** (v1 fleet is FIFO, one rider per trip) | honest for a service lift; metro upgrade in BACKLOG |

## 6 · Level of detail
| Component | Representation | Why sufficient |
|---|---|---|
| lobby arrivals | RateSchedule peak (0.010 → 0.045 → 0.015 riders/s, 3 h cycle) | morning shape |
| interfloor arrivals | Poisson 0.01/s, uniform floor pairs | background load |
| cars | Fleet n=`n_cars`, 0.5 floor/s, 8 s load + 8 s unload | travel + dwell dominate |
| floor choice | Choice over floors 2–20 (up-peak), uniform pairs (interfloor) | demand mix |

## 7 · Run design
| | |
|---|---|
| Terminating or steady-state | terminating (3 h morning window) |
| Horizon / stopping rule | 10,800 s, n=15 replications, CRN across scenarios |
| Warm-up | none (building opens empty) |
| Base time unit | seconds |

## 8 · Assumptions (limited knowledge)
| # | Assumption | Basis | Risk if wrong |
|---|---|---|---|
| A1 | peak rate 0.045 riders/s | badge-in counts, coarse | wait percentiles shift with the peak |
| A2 | 8 s load / 8 s unload | observation, small sample | dwell dominates short trips |

## 9 · Simplifications (deliberate omissions)
| # | Simplification | Why safe |
|---|---|---|
| S1 | FIFO dispatch, one rider per trip | conservative — real group control can only do better |
| S2 | no capacity limit per car | service lift, rarely more than one rider |
