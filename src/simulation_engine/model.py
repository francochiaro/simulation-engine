"""Model — the block graph, pre-run validation, and the run loop."""

from __future__ import annotations

import inspect
import json
import math
import os
from collections import deque
from collections.abc import Callable
from typing import Any

import simpy

from . import trace as ev
from .entity import Entity
from .monitors import LevelMonitor
from .rng import StreamRegistry
from .trace import Trace
from .units import TimeUnit


class ModelValidationError(Exception):
    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__(
            "Model validation failed:\n" + "\n".join(f"  - {i}" for i in issues)
        )


class RunResult:
    """Everything one run produced: KPIs, the trace, the model description,
    and consistency checks. ``to_files()`` writes the three artifacts the
    viewer consumes."""

    def __init__(
        self,
        *,
        model_json: dict,
        kpis: dict,
        trace: Trace,
        series: dict[str, list[tuple[float, float]]],
    ):
        self.model_json = model_json
        self.kpis = kpis
        self.trace = trace
        self.series = series

    def scalars(self) -> dict[str, float]:
        """Flat scalar KPIs — the unit of aggregation for replications,
        Monte Carlo, and sweeps."""
        out: dict[str, float] = {}
        for k, v in self.kpis["outputs"].items():
            out[k] = float(v)
        for name, stats in self.kpis["blocks"].items():
            for stat_name, blob in stats.items():
                if isinstance(blob, dict) and "mean" in blob:
                    if not math.isnan(blob["mean"]):
                        out[f"{name}.{stat_name}.mean"] = blob["mean"]
                elif isinstance(blob, (int, float)):
                    out[f"{name}.{stat_name}"] = float(blob)
        for name, stats in self.kpis["pools"].items():
            for stat_name, blob in stats.items():
                if isinstance(blob, dict) and "mean" in blob:
                    if not math.isnan(blob["mean"]):
                        out[f"{name}.{stat_name}.mean"] = blob["mean"]
            out[f"{name}.utilization"] = stats["utilization"]
        ent = self.kpis["entities"]
        out["entities.created"] = float(ent["created"])
        out["entities.disposed"] = float(ent["disposed"])
        out["wip.mean"] = ent["wip_mean"]
        return out

    def to_files(self, out_dir: str) -> dict[str, str]:
        os.makedirs(out_dir, exist_ok=True)
        paths = {
            "model": os.path.join(out_dir, "model.json"),
            "trace": os.path.join(out_dir, "trace.jsonl"),
            "kpis": os.path.join(out_dir, "kpis.json"),
        }
        with open(paths["model"], "w") as f:
            json.dump(self.model_json, f, indent=2)
        self.trace.to_jsonl(paths["trace"])
        with open(paths["kpis"], "w") as f:
            json.dump(self.kpis, f, indent=2, default=_json_default)
        return paths


def _json_default(o):
    if isinstance(o, float) and math.isnan(o):
        return None
    raise TypeError(f"not JSON serializable: {type(o)}")


class Model:
    """A named block graph with a declared base time unit.

    >>> m = Model("coffee_shop", time_unit="minutes")
    >>> src = Source(m, "arrivals", rate=0.5)
    >>> ... # blocks, connections
    >>> result = m.run(until=m.u.hours(8), seed=7)
    """

    def __init__(self, name: str, *, time_unit: str = "minutes"):
        self.name = name
        self.u = TimeUnit(time_unit)
        self.time_unit = self.u.base
        self.blocks: dict[str, Any] = {}
        self.pools: dict[str, Any] = {}
        self._outputs: dict[str, Callable[[Model], float]] = {}
        # Run state (populated by run()).
        self.env: simpy.Environment = None  # type: ignore[assignment]
        self.trace: Trace = None  # type: ignore[assignment]
        self.streams: StreamRegistry = None  # type: ignore[assignment]
        self.wip = LevelMonitor("wip")

    # -- construction -------------------------------------------------------

    def _register(self, block) -> None:
        if block.name in self.blocks or block.name in self.pools:
            raise ValueError(f"Duplicate block/pool name {block.name!r}")
        self.blocks[block.name] = block

    def _register_pool(self, pool) -> None:
        if pool.name in self.pools or pool.name in self.blocks:
            raise ValueError(f"Duplicate block/pool name {pool.name!r}")
        self.pools[pool.name] = pool

    def output(self, name: str, fn: Callable[[Model], float]) -> None:
        """Declare a custom scalar KPI, evaluated at the end of each run."""
        self._outputs[name] = fn

    # -- validation ----------------------------------------------------------

    def validate(self, until: float | None = ...) -> list[tuple[str, str]]:
        """Pre-run checks. Returns (level, message) tuples; ``run()`` raises
        on any 'error'. Pass ``until`` to also check the stopping rule."""
        from .blocks.route import Route
        from .blocks.sink import Sink
        from .blocks.source import Source

        issues: list[tuple[str, str]] = []
        sources = [b for b in self.blocks.values() if isinstance(b, Source)]
        sinks = [b for b in self.blocks.values() if isinstance(b, Sink)]
        if not sources:
            issues.append(("error", "Model has no Source — nothing will happen"))
        if not sinks:
            issues.append(
                ("warning", "Model has no Sink — entities are never disposed")
            )

        # Connected ports.
        for b in self.blocks.values():
            if isinstance(b, Route):
                if not b._branches:
                    issues.append(("error", f"Route {b.name!r} has no branches"))
                elif b.mode is None:
                    issues.append(
                        ("error", f"Route {b.name!r} needs mode= or weighted/conditional branches")
                    )
                elif b.mode == "condition":
                    defaults = [x for x in b._branches if x[1] is None and x[2] is None]
                    if len(defaults) != 1:
                        issues.append(
                            ("error",
                             f"Route {b.name!r}: condition mode needs exactly one "
                             f"default branch, found {len(defaults)}")
                        )
                continue
            if "out" in b.outputs and b.outputs["out"] is None:
                issues.append(
                    ("error", f"{type(b).__name__} {b.name!r}: default port 'out' is unconnected")
                )

        # Reachability from sources.
        reachable: set[str] = set()
        frontier = deque(sources)
        while frontier:
            b = frontier.popleft()
            if b.name in reachable:
                continue
            reachable.add(b.name)
            for t in b.outputs.values():
                if t is not None and t.name not in reachable:
                    frontier.append(t)
        for name in self.blocks:
            if name not in reachable:
                issues.append(("warning", f"Block {name!r} is unreachable from any Source"))

        # Seize/Release pairing.
        from .blocks.resources import Release, Seize

        releases_by_pool: dict[str, list[str]] = {}
        for b in self.blocks.values():
            if isinstance(b, Release):
                releases_by_pool.setdefault(b.pool.name, []).append(b.name)
        for b in self.blocks.values():
            if isinstance(b, Seize):
                downstream: set[str] = set()
                frontier = deque(t for t in b.outputs.values() if t is not None)
                while frontier:
                    x = frontier.popleft()
                    if x.name in downstream:
                        continue
                    downstream.add(x.name)
                    for t in x.outputs.values():
                        if t is not None:
                            frontier.append(t)
                paired = any(
                    r in downstream for r in releases_by_pool.get(b.pool.name, [])
                )
                if not paired:
                    issues.append(
                        ("error",
                         f"Seize {b.name!r} has no reachable Release for pool "
                         f"{b.pool.name!r} — units would leak")
                    )

        # Stopping rule.
        if until is not ...:
            if until is None and any(not s.bounded for s in sources):
                unbounded = [s.name for s in sources if not s.bounded]
                issues.append(
                    ("error",
                     f"No run length (until=) and source(s) {unbounded} are "
                     f"unbounded — the simulation would never stop")
                )
            if until is not None and until <= 0:
                issues.append(("error", f"until= must be > 0, got {until}"))

        return issues

    # -- runtime -------------------------------------------------------------

    def _new_entity(self, entity_type: str) -> Entity:
        self._next_id += 1
        return Entity(id=self._next_id, type=entity_type, created_at=self.env.now)

    def _entity_entered(self, t: float) -> None:
        self.entities_created += 1
        self._arrivals_stat += 1
        self.wip.increment(+1, t)

    def _entity_left(self, t: float, disposed: bool = True) -> None:
        if disposed:
            self.entities_disposed += 1
        else:
            self.entities_dropped += 1
        self.wip.increment(-1, t)

    def _drive(self, entity: Entity, block):
        env = self.env
        while block is not None:
            entity.current_block = block.name
            self.trace.emit(env.now, ev.ENTER_BLOCK, entity, block=block.name)
            res = block.process(entity)
            if inspect.isgenerator(res):
                block = yield from res
            else:
                block = res

    def _warmup_proc(self, warmup: float):
        yield self.env.timeout(warmup)
        t = self.env.now
        self._t_stats_start = t
        self._arrivals_stat = 0
        self.wip.reset(t)
        for b in self.blocks.values():
            if hasattr(b, "reset_stats"):
                b.reset_stats(t)
        for p in self.pools.values():
            p.reset_stats(t)
        self.trace.emit(t, ev.STATE, block=None, note="warmup_reset")

    def run(
        self,
        *,
        until: float | None = None,
        seed: int = 12345,
        replication: int = 0,
        warmup: float = 0.0,
        trace_level: str = "full",
    ) -> RunResult:
        issues = self.validate(until=until)
        errors = [msg for lvl, msg in issues if lvl == "error"]
        if errors:
            raise ModelValidationError(errors)
        if warmup and until is not None and warmup >= until:
            raise ModelValidationError(
                [f"warmup ({warmup}) must be smaller than until ({until})"]
            )

        self.env = simpy.Environment()
        self.trace = Trace(run_id=replication, level=trace_level)
        self.streams = StreamRegistry(seed, replication)
        self._next_id = 0
        self.entities_created = 0
        self.entities_disposed = 0
        self.entities_dropped = 0
        self._arrivals_stat = 0
        self._t_stats_start = 0.0
        self.wip = LevelMonitor("wip")

        for pool in self.pools.values():
            pool.bind()
        for block in self.blocks.values():
            block.bind()
        if warmup > 0:
            self.env.process(self._warmup_proc(warmup))

        self.env.run(until=until)
        t_end = self.env.now

        # Close all duration-weighted statistics at t_end.
        self.wip.finalize(t_end)
        for b in self.blocks.values():
            fin = getattr(b, "finalize_stats", None)
            if fin is not None:
                fin(t_end)
        for p in self.pools.values():
            p.finalize_stats(t_end)

        return RunResult(
            model_json=self.describe(),
            kpis=self._collect_kpis(t_end, seed, replication, warmup),
            trace=self.trace,
            series=self._collect_series(),
        )

    # -- results assembly ------------------------------------------------------

    def _collect_kpis(self, t_end: float, seed: int, replication: int, warmup: float) -> dict:
        from .blocks.sink import Sink

        observed = t_end - self._t_stats_start
        sinks = [b for b in self.blocks.values() if isinstance(b, Sink)]
        disposed_stat = sum(s.count for s in sinks)
        tis_values = [v for s in sinks for v in s.time_in_system.values()]
        w_mean = float(sum(tis_values) / len(tis_values)) if tis_values else math.nan
        lam = self._arrivals_stat / observed if observed > 0 else math.nan
        big_l = self.wip.mean()

        little: dict[str, float | None] = {
            "L": big_l, "lambda": lam, "W": w_mean, "residual_rel": None,
        }
        if not (math.isnan(big_l) or math.isnan(lam) or math.isnan(w_mean)):
            expected = lam * w_mean
            denom = max(abs(big_l), 1e-12)
            little["residual_rel"] = abs(big_l - expected) / denom

        blocks_stats = {}
        for b in self.blocks.values():
            stats = getattr(b, "stats", None)
            if stats is not None:
                s = stats()
                if s:
                    blocks_stats[b.name] = s
        pools_stats = {p.name: p.stats() for p in self.pools.values()}

        return {
            "run": {
                "model": self.name,
                "time_unit": self.time_unit,
                "seed": seed,
                "replication": replication,
                "t_end": t_end,
                "warmup": warmup,
                "observed_duration": observed,
            },
            "outputs": {k: fn(self) for k, fn in self._outputs.items()},
            "entities": {
                "created": self.entities_created,
                "disposed": self.entities_disposed,
                "dropped": self.entities_dropped,
                "in_system_at_end": int(self.wip.value),
                "balance_ok": self.entities_created
                == self.entities_disposed + self.entities_dropped + int(self.wip.value),
                "wip_mean": self.wip.mean(),
                "wip_max": self.wip.maximum(),
                "arrivals_observed": self._arrivals_stat,
                "disposed_observed": disposed_stat,
            },
            "blocks": blocks_stats,
            "pools": pools_stats,
            "little": little,
        }

    def _collect_series(self) -> dict[str, list[tuple[float, float]]]:
        out = {"wip": self.wip.series()}
        for b in self.blocks.values():
            for attr in ("length", "in_delay"):
                mon = getattr(b, attr, None)
                if isinstance(mon, LevelMonitor):
                    out[f"{b.name}.{attr}"] = mon.series()
        for p in self.pools.values():
            out[f"{p.name}.busy"] = p.busy.series()
        return out

    # -- description / layout ---------------------------------------------------

    def auto_layout(self) -> None:
        """Assign canvas positions to unpositioned blocks: BFS layers from
        sources, left to right."""
        from .blocks.source import Source

        depth: dict[str, int] = {}
        frontier = deque(
            (b, 0) for b in self.blocks.values() if isinstance(b, Source)
        )
        while frontier:
            b, d = frontier.popleft()
            if b.name in depth and depth[b.name] <= d:
                continue
            depth[b.name] = d
            for t in b.outputs.values():
                if t is not None:
                    frontier.append((t, d + 1))
        for name in self.blocks:
            depth.setdefault(name, 0)
        by_layer: dict[int, list[str]] = {}
        for name, d in depth.items():
            by_layer.setdefault(d, []).append(name)
        for d, names in sorted(by_layer.items()):
            for i, name in enumerate(sorted(names)):
                b = self.blocks[name]
                if b.x is None:
                    b.x = 110.0 + d * 180.0
                    b.y = 90.0 + i * 130.0

    def describe(self) -> dict:
        self.auto_layout()
        return {
            "name": self.name,
            "time_unit": self.time_unit,
            "blocks": [b.describe() for b in self.blocks.values()],
            "pools": [p.describe() for p in self.pools.values()],
        }
