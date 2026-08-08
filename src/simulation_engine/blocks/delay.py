"""Delay — holds entities for a resolved duration."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import simpy

from .. import trace as ev
from ..distributions import Distribution
from ..entity import Entity
from ..monitors import LevelMonitor
from .base import Block, EntryClaim, resolve_amount

if TYPE_CHECKING:
    from ..model import Model


class Delay(Block):
    """Delays each entity by ``duration`` (a constant, Distribution, or
    callable of the entity). ``capacity`` limits how many entities can be in
    the delay simultaneously (None = unlimited); a finite capacity creates
    backpressure that an upstream Queue absorbs."""

    def __init__(
        self,
        model: Model,
        name: str,
        *,
        duration: Distribution | float | Callable[[Entity], float],
        capacity: int | None = None,
        **hooks,
    ):
        super().__init__(model, name, **hooks)
        if capacity is not None and capacity < 1:
            raise ValueError(f"Delay {name!r}: capacity must be >= 1 or None")
        self.duration = duration
        self.capacity = capacity
        self.in_delay = LevelMonitor(f"{name}.in_delay")

    @property
    def has_entry_protocol(self) -> bool:  # type: ignore[override]
        return self.capacity is not None

    def bind(self) -> None:
        self.in_delay = LevelMonitor(f"{self.name}.in_delay")
        self._cap = (
            simpy.Resource(self.m.env, capacity=self.capacity)
            if self.capacity is not None
            else None
        )

    def occupancy(self) -> int:
        return int(self.in_delay.value)

    def reset_stats(self, t: float) -> None:
        self.in_delay.reset(t)

    def finalize_stats(self, t: float) -> None:
        self.in_delay.finalize(t)

    def stats(self) -> dict:
        return {"in_delay": self.in_delay.summary()}

    def request_entry(self):
        assert self._cap is not None
        req = self._cap.request()
        yield req
        return EntryClaim(cancel=lambda: self._cap.release(req), payload=req)

    def process(self, entity: Entity):
        env, m = self.m.env, self.m
        self._fire("on_enter", entity)

        claim: EntryClaim | None = getattr(entity, "_entry_claim", None)
        entity._entry_claim = None  # type: ignore[attr-defined]
        req = None
        if self._cap is not None:
            if claim is not None:
                req = claim.consume()
            else:
                req = self._cap.request()
                yield req

        rng = m.streams.stream(f"delay.{self.name}")
        d = resolve_amount(self.duration, entity, rng)
        self.in_delay.increment(+1, env.now)
        m.trace.emit(
            env.now, ev.DELAY_START, entity, block=self.name,
            t_start=env.now, t_end=env.now + d,
        )
        yield env.timeout(d)
        self.in_delay.increment(-1, env.now)
        m.trace.emit(env.now, ev.DELAY_END, entity, block=self.name)

        if req is not None:
            assert self._cap is not None
            self._cap.release(req)
        self._fire("on_exit", entity)
        return self.outputs["out"]

    def params(self) -> dict:
        return {
            "duration": self._describe_value(self.duration),
            "capacity": self.capacity,
        }
