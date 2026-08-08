"""Assign — set entity attributes. Consumes no time."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import numpy as np

from ..entity import Entity
from .base import Block

if TYPE_CHECKING:
    from ..model import Model


class Assign(Block):
    """Set attributes on passing entities.

    ``attrs``: dict of name -> value | Distribution | callable(entity, rng).
    ``fn``: full-custom mutation, ``fn(entity, rng)``.
    ``priority``: sets ``entity.priority`` (smaller = served first).
    """

    def __init__(
        self,
        model: Model,
        name: str,
        *,
        attrs: dict[str, Any] | None = None,
        fn: Callable[[Entity, np.random.Generator], None] | None = None,
        priority: float | Callable[[Entity], float] | None = None,
        **hooks,
    ):
        super().__init__(model, name, **hooks)
        if attrs is None and fn is None and priority is None:
            raise ValueError(f"Assign {name!r}: give attrs=, fn=, or priority=")
        self.attrs = attrs or {}
        self.fn = fn
        self.priority = priority

    def bind(self) -> None:
        pass

    def process(self, entity: Entity):
        from ..distributions import Distribution

        self._fire("on_enter", entity)
        rng = self.m.streams.stream(f"assign.{self.name}")
        for k, v in self.attrs.items():
            if isinstance(v, Distribution):
                entity.attrs[k] = v.sample(rng)
            elif callable(v):
                entity.attrs[k] = v(entity, rng)
            else:
                entity.attrs[k] = v
        if self.fn is not None:
            self.fn(entity, rng)
        if self.priority is not None:
            entity.priority = (
                self.priority(entity) if callable(self.priority) else float(self.priority)
            )
        self._fire("on_exit", entity)
        return self.outputs["out"]

    def params(self) -> dict:
        return {
            "attrs": {k: self._describe_value(v) for k, v in self.attrs.items()},
            "fn": None if self.fn is None else getattr(self.fn, "__name__", "lambda"),
            "priority": self._describe_value(self.priority)
            if self.priority is not None
            else None,
        }
