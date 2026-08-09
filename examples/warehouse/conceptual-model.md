# Conceptual model — warehouse order fulfillment

## 1 · Problem situation
Orders arrive through a peaky two-shift day and compete for pickers, dispatch
carts, forklifts, and packers. Orders that wait too long to be picked are
lost. The pain: order-to-dock time and lost demand under the midday and
evening peaks.

## 2 · Objectives
| | |
|---|---|
| Organisational aim | hit dispatch SLAs without overstaffing |
| Modeling objective | estimate order-to-dock time and lost orders for picker/cart configurations |
| Required accuracy (primary KPI) | CI half-width small enough to rank 3 vs 4 pickers |
| Audience / credibility needs | ops planning |
| Study constraints | none |

## 3 · Outputs (responses)
| KPI | Type | Determines |
|---|---|---|
| `order_to_dock_mean` | mean (min) | SLA achievement |
| `orders_lost` | count per day | demand at risk |
| `orders_dispatched` | count per day | throughput |
| packer availability | fraction | breakdown exposure |

## 4 · Experimental factors (inputs)
| Factor | Range / values | Expected direction of effect |
|---|---|---|
| `n_pickers` | 1 – 8 | ↑pickers → shorter pick queue, fewer lost |
| `cart_size` | 2 – 12 | ↑size → better forklift batching, longer wait-to-fill |

## 5 · Scope
| Component | In / out | Justification |
|---|---|---|
| picking, carts, forklift haul, packing | in | the order path |
| replenishment / inbound | **out** | stock assumed available at pick faces |
| packer breakdowns | in | availability moves the bottleneck |

## 6 · Level of detail
| Component | Representation | Why sufficient |
|---|---|---|
| arrivals | RateSchedule (nonstationary Poisson over the day) | captures both peaks |
| picking | Service, c=`n_pickers`, duration ~ Lognormal(mean=6, sd=3) | right-skewed pick times |
| pick patience | Queue max_wait=45 min → lost | lost-demand mechanism |
| dispatch carts | Batch size=`cart_size`, timeout 20 min | partial carts still move |
| forklift | Fleet n=2 + Ride 0→120 m | travel + contention |
| packing | Service, c=3, duration ~ Triangular(1.5, 2.5, 5), mtbf/mttr on the pool | breakdowns matter, detail doesn't |

## 7 · Run design
| | |
|---|---|
| Terminating or steady-state | terminating (one 16 h day) |
| Horizon / stopping rule | 960 min, n=15 replications, CRN across scenarios |
| Warm-up | none (day starts empty by design) |
| Base time unit | minutes |

## 8 · Assumptions (limited knowledge)
| # | Assumption | Basis | Risk if wrong |
|---|---|---|---|
| A1 | pick time Lognormal(6, 3) | expert estimate, no data | tails understated → congestion optimistic |
| A2 | order patience 45 min | policy, not measured | lost-order count shifts |
| A3 | packer mtbf/mttr Exponential(180)/Triangular(5,12,30) | maintenance log anecdotes | availability estimate moves |

## 9 · Simplifications (deliberate omissions)
| # | Simplification | Why safe |
|---|---|---|
| S1 | single aggregated pick zone | zone travel folded into pick-time distribution |
| S2 | forklift path as straight 120 m | contention, not routing, drives the KPI |
