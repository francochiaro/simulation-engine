"""Sink — disposes of entities and records time in system."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import trace as ev
from ..monitors import TallyMonitor
from .base import Block

if TYPE_CHECKING:
    from ..model import Model


class Sink(Block):
    def __init__(self, model: Model, name: str, **hooks):
        super().__init__(model, name, **hooks)
        del self.outputs["out"]  # nothing flows out of a sink
        self.count = 0
        self.time_in_system = TallyMonitor(f"{name}.time_in_system")

    def bind(self) -> None:
        self.count = 0
        self.time_in_system = TallyMonitor(f"{self.name}.time_in_system")

    def process(self, entity):
        env, m = self.m.env, self.m
        self._fire("on_enter", entity)
        tis = env.now - entity.created_at
        self.time_in_system.observe(tis)
        self.count += 1
        if entity.tokens and any(entity.tokens.values()):
            held = {k: len(v) for k, v in entity.tokens.items() if v}
            raise RuntimeError(
                f"{entity!r} reached sink {self.name!r} still holding resource "
                f"units {held} — every Seize needs a matching Release "
                f"(or use Service, which cannot leak)"
            )
        m.trace.emit(env.now, ev.DEPART, entity, block=self.name, time_in_system=tis)
        m._entity_left(env.now)
        return None

    def reset_stats(self, t: float) -> None:
        self.count = 0
        self.time_in_system.reset(t)

    def stats(self) -> dict:
        return {
            "count": self.count,
            "time_in_system": self.time_in_system.summary(),
        }
