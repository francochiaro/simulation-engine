"""Block base class — Layer 2's foundation.

Blocks are configuration objects with stable names, optional canvas
positions, typed parameters, and named output ports. All SimPy machinery
lives *inside* block implementations: model authors (human or agent) never
write ``yield``.

Runtime state is created in ``bind()`` at the start of every run, so a model
can be run repeatedly (replications) from one description.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import numpy as np

from ..distributions import Distribution
from ..entity import Entity

if TYPE_CHECKING:
    from ..model import Model


def resolve_amount(
    value: Distribution | float | Callable[[Entity], float],
    entity: Entity,
    rng: np.random.Generator,
) -> float:
    """Resolve an expression-valued parameter: a constant, a distribution
    draw, or a callable of the entity (AnyLogic's dynamic-expression
    pattern)."""
    if isinstance(value, Distribution):
        return float(value.sample(rng))
    if callable(value):
        return float(value(entity))
    return float(value)


class EntryClaim:
    """A reserved slot in a downstream block (used by Queue's pump so the
    head of the queue only advances when the downstream block can take it)."""

    def __init__(self, cancel: Callable[[], None], payload: Any = None):
        self._cancel = cancel
        self.payload = payload
        self.consumed = False

    def cancel(self) -> None:
        if not self.consumed:
            self.consumed = True
            self._cancel()

    def consume(self) -> Any:
        self.consumed = True
        return self.payload


class Block:
    """Base class for all blocks."""

    # Blocks that limit concurrent occupancy override this and implement
    # ``request_entry`` so upstream Queues can reserve a slot.
    has_entry_protocol = False

    def __init__(self, model: Model, name: str, **hooks: Callable):
        self.m = model
        self.name = name
        self.x: float | None = None
        self.y: float | None = None
        self.outputs: dict[str, Block | None] = {"out": None}
        # Lifecycle hooks: on_enter(entity), on_exit(entity), plus
        # block-specific ones (on_seize, on_release, on_timeout...).
        self.hooks: dict[str, Callable] = {}
        for k, fn in hooks.items():
            if not k.startswith("on_") or not callable(fn):
                raise ValueError(
                    f"{name}: unknown keyword {k!r} — hooks are callables named on_*"
                )
            self.hooks[k] = fn
        model._register(self)

    # -- graph building ---------------------------------------------------

    def to(self, target: Block, port: str = "out") -> Block:
        """Connect an output port to a target block. Returns the target so
        connections chain: ``a.to(b).to(c)``."""
        if port not in self.outputs:
            raise ValueError(
                f"{self.name} has no port {port!r} (ports: {sorted(self.outputs)})"
            )
        self.outputs[port] = target
        return target

    def __rshift__(self, target: Block) -> Block:
        return self.to(target)

    def at(self, x: float, y: float) -> Block:
        """Set the canvas position for the viewer. Returns self."""
        self.x, self.y = float(x), float(y)
        return self

    # -- runtime -----------------------------------------------------------

    def bind(self) -> None:
        """Create per-run runtime state. Called by Model.run() before the
        simulation starts; must fully reset the block."""

    def process(self, entity: Entity):
        """Handle one entity. Either returns the next block directly (instant
        blocks) or is a generator yielding SimPy events and returning the
        next block. Returning None absorbs the entity."""
        raise NotImplementedError

    def request_entry(self):
        """Generator reserving a slot for one entity; returns an EntryClaim
        or None. Only meaningful when has_entry_protocol is True."""
        raise NotImplementedError

    def occupancy(self) -> int | None:
        """Current number of entities held (for shortest-queue routing and
        the post-run sanity report). None if not applicable."""
        return None

    def _fire(self, hook: str, entity: Entity) -> None:
        fn = self.hooks.get(hook)
        if fn is not None:
            fn(entity)

    # -- serialization ------------------------------------------------------

    def params(self) -> dict:
        """Block parameters for model.json (viewer + audit). Distributions
        self-describe; callables are labeled as such."""
        return {}

    def describe(self) -> dict:
        return {
            "name": self.name,
            "type": type(self).__name__,
            "x": self.x,
            "y": self.y,
            "outputs": {
                port: (b.name if b is not None else None)
                for port, b in self.outputs.items()
            },
            "params": self.params(),
        }

    @staticmethod
    def _describe_value(v: Any) -> Any:
        if isinstance(v, Distribution):
            return v.describe()
        if callable(v):
            return {"type": "expression", "name": getattr(v, "__name__", "lambda")}
        return v

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.name!r})"
