"""Resources — identity-bearing capacity pools and the blocks that use them.

Every unit in a :class:`ResourcePool` has a stable identity (``pool_name#i``),
never an anonymous capacity slot: the trace can then say *which* server an
entity is on, and the pool reports per-unit busy time. (This is the vidigi
lesson — anonymous SimPy resources cannot drive per-server animation.)

:class:`Service` (seize → delay → release, fused) is the block model authors
should reach for by default: it cannot leak resource units. Standalone
:class:`Seize`/:class:`Release` exist for spans (seize at A, release at B)
and are validated for pairing at model-check time.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import simpy

from .. import trace as ev
from ..distributions import Distribution
from ..entity import Entity
from ..monitors import LevelMonitor, TallyMonitor
from .base import Block, EntryClaim, resolve_amount

if TYPE_CHECKING:
    from ..model import Model


class ResourcePool:
    """A pool of ``capacity`` identical, individually identified units.

    Not a block — pools sit beside the flowchart and are referenced by
    Service/Seize/Release blocks. Requests are granted in priority order
    (smaller = first; FIFO within ties).
    """

    def __init__(self, model: Model, name: str, capacity: int):
        if capacity < 1:
            raise ValueError(f"ResourcePool {name!r}: capacity must be >= 1")
        self.m = model
        self.name = name
        self.capacity = capacity
        self.busy = LevelMonitor(f"{name}.busy")
        self.queue_len = LevelMonitor(f"{name}.queue")
        self.wait = TallyMonitor(f"{name}.wait")
        self.unit_busy_time: dict[str, float] = {}
        model._register_pool(self)

    def bind(self) -> None:
        env = self.m.env
        self._res = simpy.PriorityResource(env, capacity=self.capacity)
        self._free_units = [f"{self.name}#{i}" for i in range(1, self.capacity + 1)]
        self._seized_at: dict[str, float] = {}
        self.busy = LevelMonitor(f"{self.name}.busy")
        self.queue_len = LevelMonitor(f"{self.name}.queue")
        self.wait = TallyMonitor(f"{self.name}.wait")
        self.unit_busy_time = {u: 0.0 for u in self._free_units}

    def utilization(self) -> float:
        return self.busy.mean() / self.capacity

    def reset_stats(self, t: float) -> None:
        self.busy.reset(t)
        self.queue_len.reset(t)
        self.wait.reset(t)
        self.unit_busy_time = {u: 0.0 for u in self.unit_busy_time}
        # Re-open busy intervals for units seized before the warmup boundary,
        # so their post-warmup busy time still accrues.
        self._seized_at = {u: t for u in self._seized_at}

    def finalize_stats(self, t: float) -> None:
        self.busy.finalize(t)
        self.queue_len.finalize(t)
        for unit, t0 in self._seized_at.items():
            self.unit_busy_time[unit] = self.unit_busy_time.get(unit, 0.0) + (t - t0)
        self._seized_at = {u: t for u in self._seized_at}

    def stats(self) -> dict:
        return {
            "busy": self.busy.summary(),
            "queue": self.queue_len.summary(),
            "wait": self.wait.summary(),
            "utilization": self.utilization(),
            "capacity": self.capacity,
            "unit_busy_time": dict(self.unit_busy_time),
        }

    def describe(self) -> dict:
        return {"name": self.name, "capacity": self.capacity}

    # -- acquisition protocol (used by Service / Seize) --------------------

    def _acquire(self, priority: float = 0.0):
        """Generator: wait for one unit; returns (request, unit_id)."""
        env = self.m.env
        req = self._res.request(priority=priority)
        t0 = env.now
        self.queue_len.increment(+1, t0)
        yield req
        self.queue_len.increment(-1, env.now)
        self.wait.observe(env.now - t0)
        unit = self._free_units.pop(0)
        self._seized_at[unit] = env.now
        self.busy.increment(+1, env.now)
        return req, unit

    def _free(self, req, unit: str) -> None:
        env = self.m.env
        self.unit_busy_time[unit] = self.unit_busy_time.get(unit, 0.0) + (
            env.now - self._seized_at.pop(unit, env.now)
        )
        self._free_units.append(unit)
        self.busy.increment(-1, env.now)
        self._res.release(req)


class Service(Block):
    """Seize one unit of ``resource`` → delay by ``duration`` → release.

    ``resource`` may be a ResourcePool (shared with other blocks) or an int
    capacity (a dedicated pool named ``<name>.servers`` is created). Waiting
    entities queue inside the block in priority order (``entity.priority``,
    smaller first); put an explicit Queue upstream when the waiting area
    should be visible/limited/reneging.
    """

    has_entry_protocol = True

    def __init__(
        self,
        model: Model,
        name: str,
        *,
        duration: Distribution | float | Callable[[Entity], float],
        resource: ResourcePool | int = 1,
        **hooks,
    ):
        super().__init__(model, name, **hooks)
        if isinstance(resource, int):
            resource = ResourcePool(model, f"{name}.servers", capacity=resource)
        self.pool = resource
        self.duration = duration

    def bind(self) -> None:
        pass  # the pool binds itself; Service holds no other runtime state

    def occupancy(self) -> int:
        # Entities waiting + being served on this block's pool.
        return int(self.pool.queue_len.value + self.pool.busy.value)

    def request_entry(self):
        # Reserve a server before the upstream queue releases the entity.
        # Priority is unknowable here (slot, not entity) — when discipline
        # matters, it lives in the upstream Queue.
        req, unit = yield from self.pool._acquire(priority=0.0)
        return EntryClaim(
            cancel=lambda: self.pool._free(req, unit), payload=(req, unit)
        )

    def process(self, entity: Entity):
        env, m = self.m.env, self.m
        self._fire("on_enter", entity)

        claim: EntryClaim | None = getattr(entity, "_entry_claim", None)
        entity._entry_claim = None  # type: ignore[attr-defined]
        if claim is not None:
            req, unit = claim.consume()
        else:
            m.trace.emit(
                env.now, ev.SEIZE_REQUEST, entity, block=self.name,
                resource=self.pool.name,
            )
            req, unit = yield from self.pool._acquire(priority=entity.priority)
        self._fire("on_seize", entity)
        m.trace.emit(
            env.now, ev.SEIZE, entity, block=self.name,
            resource=self.pool.name, resource_unit=unit,
        )

        rng = m.streams.stream(f"service.{self.name}")
        d = resolve_amount(self.duration, entity, rng)
        m.trace.emit(
            env.now, ev.DELAY_START, entity, block=self.name,
            resource_unit=unit, t_start=env.now, t_end=env.now + d,
        )
        yield env.timeout(d)
        m.trace.emit(env.now, ev.DELAY_END, entity, block=self.name)

        self.pool._free(req, unit)
        self._fire("on_release", entity)
        m.trace.emit(
            env.now, ev.RELEASE, entity, block=self.name,
            resource=self.pool.name, resource_unit=unit,
        )
        self._fire("on_exit", entity)
        return self.outputs["out"]

    def params(self) -> dict:
        return {
            "duration": self._describe_value(self.duration),
            "resource": self.pool.name,
            "capacity": self.pool.capacity,
        }


class Seize(Block):
    """Seize one unit of a pool and carry it (for spans: seize at A, release
    at B). The model validator requires a reachable Release for the same
    pool; the Sink refuses entities still holding units."""

    def __init__(self, model: Model, name: str, *, resource: ResourcePool, **hooks):
        super().__init__(model, name, **hooks)
        self.pool = resource

    def bind(self) -> None:
        pass

    def process(self, entity: Entity):
        env, m = self.m.env, self.m
        self._fire("on_enter", entity)
        m.trace.emit(
            env.now, ev.SEIZE_REQUEST, entity, block=self.name, resource=self.pool.name
        )
        req, unit = yield from self.pool._acquire(priority=entity.priority)
        entity.tokens.setdefault(self.pool.name, []).append((req, unit))
        self._fire("on_seize", entity)
        m.trace.emit(
            env.now, ev.SEIZE, entity, block=self.name,
            resource=self.pool.name, resource_unit=unit,
        )
        self._fire("on_exit", entity)
        return self.outputs["out"]

    def params(self) -> dict:
        return {"resource": self.pool.name}


class Release(Block):
    """Release units of a pool previously seized by a Seize block."""

    def __init__(self, model: Model, name: str, *, resource: ResourcePool, **hooks):
        super().__init__(model, name, **hooks)
        self.pool = resource

    def bind(self) -> None:
        pass

    def process(self, entity: Entity):
        env, m = self.m.env, self.m
        self._fire("on_enter", entity)
        held = entity.tokens.get(self.pool.name, [])
        if not held:
            raise RuntimeError(
                f"{entity!r} reached Release {self.name!r} holding no unit of "
                f"pool {self.pool.name!r} — check the Seize/Release pairing"
            )
        req, unit = held.pop()
        self.pool._free(req, unit)
        self._fire("on_release", entity)
        m.trace.emit(
            env.now, ev.RELEASE, entity, block=self.name,
            resource=self.pool.name, resource_unit=unit,
        )
        self._fire("on_exit", entity)
        return self.outputs["out"]

    def params(self) -> dict:
        return {"resource": self.pool.name}
