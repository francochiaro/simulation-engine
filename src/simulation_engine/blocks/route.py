"""Route — N-way routing by probability, condition, round-robin, or
shortest queue. Consumes no time."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ..entity import Entity
from .base import Block

if TYPE_CHECKING:
    from ..model import Model

MODES = ("probability", "condition", "round_robin", "shortest_queue")


class Route(Block):
    """Add branches with :meth:`add`. Exactly one mode per Route:

    - probability: ``add(target, weight=0.7)`` — weights normalized
    - condition:   ``add(target, when=lambda e: e.attrs["vip"])`` — first
      true wins; one ``add(target)`` with no ``when`` is the required default
    - round_robin: ``Route(..., mode="round_robin")`` + plain ``add(target)``
    - shortest_queue: picks the branch whose target reports the smallest
      occupancy (Queue length, Service waiting+busy)
    """

    def __init__(self, model: Model, name: str, *, mode: str | None = None, **hooks):
        super().__init__(model, name, **hooks)
        del self.outputs["out"]
        self.mode = mode
        self._branches: list[tuple[Block, float | None, Callable | None]] = []

    def add(
        self,
        target: Block,
        *,
        weight: float | None = None,
        when: Callable[[Entity], bool] | None = None,
    ) -> Route:
        if weight is not None and when is not None:
            raise ValueError(f"Route {self.name!r}: a branch takes weight= OR when=, not both")
        if weight is not None:
            if weight <= 0:
                raise ValueError(f"Route {self.name!r}: weight must be > 0")
            self._infer_mode("probability")
        elif when is not None:
            self._infer_mode("condition")
        self._branches.append((target, weight, when))
        self.outputs[f"out{len(self._branches)}"] = target
        return self

    def _infer_mode(self, mode: str) -> None:
        if self.mode is None:
            self.mode = mode
        elif self.mode != mode:
            raise ValueError(
                f"Route {self.name!r}: mixed branch kinds — mode is {self.mode!r} "
                f"but a branch implies {mode!r}"
            )

    def bind(self) -> None:
        self._rr_index = 0
        if not self._branches:
            raise ValueError(f"Route {self.name!r} has no branches — call add()")
        if self.mode is None:
            raise ValueError(
                f"Route {self.name!r}: set mode= or give branches weight=/when="
            )
        if self.mode == "probability":
            if any(w is None for _, w, _ in self._branches):
                raise ValueError(
                    f"Route {self.name!r}: every branch needs weight= in probability mode"
                )
            total = sum(w for _, w, _ in self._branches if w is not None)
            self._probs = [w / total for _, w, _ in self._branches if w is not None]
        if self.mode == "condition":
            defaults = [b for b in self._branches if b[2] is None and b[1] is None]
            if len(defaults) != 1:
                raise ValueError(
                    f"Route {self.name!r}: condition mode needs exactly one default "
                    f"branch (add(target) with no when=), found {len(defaults)}"
                )

    def process(self, entity: Entity):
        self._fire("on_enter", entity)
        if self.mode == "probability":
            rng = self.m.streams.stream(f"route.{self.name}")
            i = int(rng.choice(len(self._branches), p=self._probs))
            target = self._branches[i][0]
        elif self.mode == "condition":
            target = None
            default = None
            for block, _, when in self._branches:
                if when is None:
                    default = block
                elif target is None and when(entity):
                    target = block
            if target is None:
                target = default
        elif self.mode == "round_robin":
            target = self._branches[self._rr_index % len(self._branches)][0]
            self._rr_index += 1
        else:  # shortest_queue
            def occ(block: Block) -> int:
                o = block.occupancy()
                return o if o is not None else 0

            target = min((b for b, _, _ in self._branches), key=occ)
        self._fire("on_exit", entity)
        return target

    def params(self) -> dict:
        return {
            "mode": self.mode,
            "branches": [
                {
                    "target": b.name,
                    "weight": w,
                    "when": None if fn is None else getattr(fn, "__name__", "lambda"),
                }
                for b, w, fn in self._branches
            ],
        }
