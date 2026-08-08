"""Flow-control and measurement blocks: Gate, Move, TimeMeasure pair."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ..distributions import Distribution
from ..entity import Entity
from ..monitors import TallyMonitor
from .base import Block
from .delay import Delay

if TYPE_CHECKING:
    from ..model import Model


class Gate(Block):
    """Blocks or releases the flow. Control it from hooks or model code
    (``gate.open()`` / ``gate.close()``), or give ``cycle=(open_for,
    closed_for)`` for an automatic alternation (shift gates, traffic
    lights)."""

    def __init__(
        self,
        model: Model,
        name: str,
        *,
        initially_open: bool = True,
        cycle: tuple[float, float] | None = None,
        **hooks,
    ):
        super().__init__(model, name, **hooks)
        if cycle is not None and (cycle[0] <= 0 or cycle[1] <= 0):
            raise ValueError(f"Gate {name!r}: cycle durations must be > 0")
        self.initially_open = initially_open
        self.cycle = cycle

    def bind(self) -> None:
        self.is_open = self.initially_open
        self._release = self.m.env.event()
        if self.is_open:
            self._release.succeed()
        if self.cycle is not None:
            self.m.env.process(self._cycler())

    def open(self) -> None:
        self.is_open = True
        if not self._release.triggered:
            self._release.succeed()

    def close(self) -> None:
        self.is_open = False
        self._release = self.m.env.event()

    def _cycler(self):
        env = self.m.env
        assert self.cycle is not None
        open_for, closed_for = self.cycle
        if not self.is_open:
            yield env.timeout(closed_for)
            self.open()
        while True:
            yield env.timeout(open_for)
            self.close()
            yield env.timeout(closed_for)
            self.open()

    def process(self, entity: Entity):
        self._fire("on_enter", entity)
        while not self.is_open:
            yield self._release
        self._fire("on_exit", entity)
        return self.outputs["out"]

    def params(self) -> dict:
        return {"initially_open": self.initially_open, "cycle": self.cycle}


class Move(Delay):
    """A Delay that reads as travel: fixed duration, or distance/speed."""

    def __init__(
        self,
        model: Model,
        name: str,
        *,
        duration: Distribution | float | Callable[[Entity], float] | None = None,
        distance: float | None = None,
        speed: float | None = None,
        **hooks,
    ):
        if duration is None:
            if distance is None or speed is None or speed <= 0:
                raise ValueError(
                    f"Move {name!r}: give duration=, or distance= and speed="
                )
            duration = distance / speed
        super().__init__(model, name, duration=duration, **hooks)


class TimeMeasureStart(Block):
    """Stamp passing entities; a paired TimeMeasureEnd tallies the elapsed
    time. ``measure`` names the pair (defaults to this block's name)."""

    def __init__(self, model: Model, name: str, *, measure: str | None = None, **hooks):
        super().__init__(model, name, **hooks)
        self.measure = measure or name

    def bind(self) -> None:
        pass

    def process(self, entity: Entity):
        entity.stamps[self.measure] = self.m.env.now
        return self.outputs["out"]

    def params(self) -> dict:
        return {"measure": self.measure}


class TimeMeasureEnd(Block):
    def __init__(self, model: Model, name: str, *, measure: str, **hooks):
        super().__init__(model, name, **hooks)
        self.measure = measure
        self.elapsed = TallyMonitor(f"{name}.elapsed")

    def bind(self) -> None:
        self.elapsed = TallyMonitor(f"{self.name}.elapsed")

    def reset_stats(self, t: float) -> None:
        self.elapsed.reset(t)

    def stats(self) -> dict:
        return {"elapsed": self.elapsed.summary()}

    def process(self, entity: Entity):
        t0 = entity.stamps.pop(self.measure, None)
        if t0 is None:
            raise RuntimeError(
                f"{entity!r} reached TimeMeasureEnd {self.name!r} without a "
                f"{self.measure!r} stamp — is the paired TimeMeasureStart on "
                f"every path into this block?"
            )
        self.elapsed.observe(self.m.env.now - t0)
        return self.outputs["out"]

    def params(self) -> dict:
        return {"measure": self.measure}
