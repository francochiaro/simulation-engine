"""Batch / Unbatch — group entities into a container and split them again.

Members are not destroyed: their processes suspend inside the container and
resume at the Unbatch block (or are disposed with the container at a Sink).
Entity accounting stays exact — members never leave the system while batched.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import trace as ev
from ..distributions import Distribution
from ..entity import Entity
from ..monitors import LevelMonitor
from .base import Block, resolve_amount

if TYPE_CHECKING:
    from ..model import Model


class Batch(Block):
    """Accumulate ``size`` entities, then emit one container entity holding
    them. ``timeout`` (optional) emits a partial batch when the oldest waiting
    member has waited that long — never an empty one.

    The container's ``attrs["members"]`` lists the member entities;
    ``attrs["batch_of"]`` is this block's name.
    """

    def __init__(
        self,
        model: Model,
        name: str,
        *,
        size: int,
        timeout: Distribution | float | None = None,
        batch_type: str | None = None,
        **hooks,
    ):
        super().__init__(model, name, **hooks)
        if size < 1:
            raise ValueError(f"Batch {name!r}: size must be >= 1")
        self.size = size
        self.timeout = timeout
        self.batch_type = batch_type or f"{name}.batch"
        self.waiting = LevelMonitor(f"{name}.waiting")

    def bind(self) -> None:
        self._buffer: list[tuple[Entity, object]] = []  # (entity, resume event)
        self._generation = 0
        self.waiting = LevelMonitor(f"{self.name}.waiting")

    def occupancy(self) -> int:
        return len(self._buffer)

    def finalize_stats(self, t: float) -> None:
        self.waiting.finalize(t)

    def reset_stats(self, t: float) -> None:
        self.waiting.reset(t)

    def stats(self) -> dict:
        return {"waiting": self.waiting.summary()}

    def _form_batch(self) -> None:
        env, m = self.m.env, self.m
        members = self._buffer
        self._buffer = []
        self.waiting.set(0, env.now)
        container = m._new_entity(self.batch_type)
        container.attrs["members"] = [e for e, _ in members]
        container.attrs["batch_of"] = self.name
        container._member_events = [evt for _, evt in members]  # type: ignore[attr-defined]
        m._entity_entered(env.now)
        m.trace.emit(
            env.now, ev.STATE, container, block=self.name,
            note="batch_formed", size=len(members),
            member_ids=[e.id for e, _ in members],
        )
        target = self.outputs["out"]
        if target is not None:
            env.process(m._drive(container, target))

    def _timeout_timer(self, generation: int):
        env = self.m.env
        rng = self.m.streams.stream(f"batch.{self.name}.timeout")
        assert self.timeout is not None
        d = resolve_amount(self.timeout, None, rng)  # type: ignore[arg-type]
        yield env.timeout(d)
        # Fire only if the same batch generation is still accumulating.
        if self._generation == generation and self._buffer:
            self._form_batch()
            self._generation += 1

    def process(self, entity: Entity):
        env, m = self.m.env, self.m
        self._fire("on_enter", entity)
        resume = env.event()
        self._buffer.append((entity, resume))
        self.waiting.set(len(self._buffer), env.now)
        m.trace.emit(env.now, ev.QUEUE_JOIN, entity, block=self.name, qlen=len(self._buffer))
        if len(self._buffer) >= self.size:
            self._form_batch()
            self._generation += 1
        elif self.timeout is not None and len(self._buffer) == 1:
            env.process(self._timeout_timer(self._generation))
        # Suspend until Unbatch (value = the block to continue at) or a Sink
        # disposes the container (value = None).
        next_block = yield resume
        self._fire("on_exit", entity)
        return next_block

    def params(self) -> dict:
        return {
            "size": self.size,
            "timeout": self._describe_value(self.timeout) if self.timeout is not None else None,
        }


class Unbatch(Block):
    """Dissolve a container from a Batch block: members resume flowing from
    this block's ``out`` port; the container ceases to exist."""

    def __init__(self, model: Model, name: str, **hooks):
        super().__init__(model, name, **hooks)

    def bind(self) -> None:
        pass

    def process(self, entity: Entity):
        env, m = self.m.env, self.m
        self._fire("on_enter", entity)
        events = getattr(entity, "_member_events", None)
        if events is None:
            raise RuntimeError(
                f"{entity!r} reached Unbatch {self.name!r} but is not a batch "
                f"container (route only Batch output here)"
            )
        m.trace.emit(
            env.now, ev.STATE, entity, block=self.name, note="unbatch",
            size=len(events),
        )
        target = self.outputs["out"]
        for evt in events:
            evt.succeed(target)
        # The container dissolves (members remain in-system).
        m._entity_left(env.now, disposed=True)
        self._fire("on_exit", entity)
        return None

    def params(self) -> dict:
        return {}
