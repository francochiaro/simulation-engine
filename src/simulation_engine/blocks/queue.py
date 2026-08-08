"""Queue — an explicit, inspectable waiting area.

Owned by the library (not a bare SimPy Resource) so it can be animated,
report time-weighted length statistics, honor disciplines, and support
balking and reneging. A pump process advances the head of the queue only
when the downstream block grants an entry slot — so entities visibly wait
*here*, not inside the downstream block.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from .. import trace as ev
from ..distributions import Distribution
from ..entity import Entity
from ..monitors import LevelMonitor, TallyMonitor
from .base import Block, resolve_amount

if TYPE_CHECKING:
    from ..model import Model

DISCIPLINES = ("fifo", "lifo", "priority")


class _QItem:
    __slots__ = ("entity", "proceed", "joined_at")

    def __init__(self, entity: Entity, proceed, joined_at: float):
        self.entity = entity
        self.proceed = proceed
        self.joined_at = joined_at


class Queue(Block):
    """Ports: ``out`` (default), ``balk`` (arrivals when full), ``timeout``
    (entities whose ``max_wait`` expired). Unconnected balk/timeout ports
    drop the entity (with a trace event and a counter — never silently).

    ``discipline``: "fifo" | "lifo" | "priority" (uses ``priority_key`` or
    ``entity.priority``; smaller = served first, FIFO within ties).
    """

    def __init__(
        self,
        model: Model,
        name: str,
        *,
        capacity: int | None = None,
        discipline: str = "fifo",
        priority_key: Callable[[Entity], float] | None = None,
        max_wait: Distribution | float | Callable[[Entity], float] | None = None,
        **hooks,
    ):
        super().__init__(model, name, **hooks)
        self.outputs["balk"] = None
        self.outputs["timeout"] = None
        if capacity is not None and capacity < 1:
            raise ValueError(f"Queue {name!r}: capacity must be >= 1 or None")
        if discipline not in DISCIPLINES:
            raise ValueError(
                f"Queue {name!r}: discipline must be one of {DISCIPLINES}"
            )
        if priority_key is not None and discipline != "priority":
            raise ValueError(
                f"Queue {name!r}: priority_key requires discipline='priority'"
            )
        self.capacity = capacity
        self.discipline = discipline
        self.priority_key = priority_key
        self.max_wait = max_wait
        # Runtime state (recreated in bind()).
        self._items: list[_QItem] = []
        self.balked = 0
        self.reneged = 0
        self.length = LevelMonitor(f"{name}.length")
        self.wait = TallyMonitor(f"{name}.wait")

    def bind(self) -> None:
        self._items = []
        self.balked = 0
        self.reneged = 0
        self.length = LevelMonitor(f"{self.name}.length")
        self.wait = TallyMonitor(f"{self.name}.wait")
        self._sleep = None
        self.m.env.process(self._pump())

    def occupancy(self) -> int:
        return len(self._items)

    def reset_stats(self, t: float) -> None:
        self.length.reset(t)
        self.wait.reset(t)
        self.balked = 0
        self.reneged = 0

    def finalize_stats(self, t: float) -> None:
        self.length.finalize(t)

    def stats(self) -> dict:
        return {
            "length": self.length.summary(),
            "wait": self.wait.summary(),
            "balked": self.balked,
            "reneged": self.reneged,
        }

    # -- mechanics ---------------------------------------------------------

    def _pop_head(self) -> _QItem:
        if self.discipline == "lifo":
            return self._items.pop()
        if self.discipline == "priority":
            key = self.priority_key or (lambda e: e.priority)
            best = min(range(len(self._items)), key=lambda i: key(self._items[i].entity))
            return self._items.pop(best)
        return self._items.pop(0)

    def _wake(self) -> None:
        if self._sleep is not None and not self._sleep.triggered:
            self._sleep.succeed()

    def _pump(self):
        env = self.m.env
        while True:
            if not self._items:
                self._sleep = env.event()
                yield self._sleep
                continue
            down = self.outputs["out"]
            if down is not None and down.has_entry_protocol:
                claim = yield from down.request_entry()
            else:
                claim = None
            if not self._items:
                # Everyone reneged while we waited for the slot.
                if claim is not None:
                    claim.cancel()
                continue
            item = self._pop_head()
            self.length.set(len(self._items), env.now)
            item.entity._entry_claim = claim  # type: ignore[attr-defined]
            item.proceed.succeed()

    def process(self, entity: Entity):
        env, m = self.m.env, self.m
        self._fire("on_enter", entity)

        if self.capacity is not None and len(self._items) >= self.capacity:
            self.balked += 1
            m.trace.emit(env.now, ev.BALK, entity, block=self.name)
            target = self.outputs["balk"]
            if target is None:
                m._entity_left(env.now, disposed=False)
            return target

        item = _QItem(entity, env.event(), env.now)
        self._items.append(item)
        self.length.set(len(self._items), env.now)
        m.trace.emit(
            env.now, ev.QUEUE_JOIN, entity, block=self.name, qlen=len(self._items)
        )
        self._wake()

        if self.max_wait is not None:
            rng = m.streams.stream(f"queue.{self.name}.renege")
            patience = resolve_amount(self.max_wait, entity, rng)
            result = yield item.proceed | env.timeout(patience)
            if item.proceed not in result:
                self._items.remove(item)
                self.length.set(len(self._items), env.now)
                self.reneged += 1
                waited = env.now - item.joined_at
                self.wait.observe(waited)
                m.trace.emit(
                    env.now, ev.RENEGE, entity, block=self.name, waited=waited,
                    qlen=len(self._items),
                )
                self._fire("on_timeout", entity)
                target = self.outputs["timeout"]
                if target is None:
                    m._entity_left(env.now, disposed=False)
                return target
        else:
            yield item.proceed

        waited = env.now - item.joined_at
        self.wait.observe(waited)
        m.trace.emit(
            env.now, ev.QUEUE_LEAVE, entity, block=self.name, waited=waited,
            qlen=len(self._items),
        )
        self._fire("on_exit", entity)
        return self.outputs["out"]

    def params(self) -> dict:
        return {
            "capacity": self.capacity,
            "discipline": self.discipline,
            "max_wait": self._describe_value(self.max_wait) if self.max_wait is not None else None,
        }
