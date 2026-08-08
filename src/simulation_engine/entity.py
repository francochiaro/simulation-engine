"""Entities — the objects that flow through a model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Entity:
    """A single flowing object (customer, order, pallet, elevator call...).

    ``attrs`` is the model author's space; everything else is engine-owned.
    """

    id: int
    type: str
    created_at: float
    attrs: dict[str, Any] = field(default_factory=dict)

    # Engine-owned bookkeeping.
    current_block: str | None = None
    priority: float = 0.0
    # Seized resource units, keyed by pool name (see ResourcePool).
    tokens: dict[str, list] = field(default_factory=dict)
    # TimeMeasure start stamps, keyed by measure name.
    stamps: dict[str, float] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"Entity({self.type}#{self.id})"
